import json
import os
import re
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from psycopg import Connection, connect

app = FastAPI(title="JARVIS AI Service", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "120"))
DESKTOP_AGENT_URL = os.environ.get("DESKTOP_AGENT_URL", "http://127.0.0.1:8765").rstrip("/")
USER_NAME = os.environ.get("JARVIS_USER_NAME", "Teja")
CONTEXT_LOCK = Lock()
DB_CONFIG = {
    "host": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    "port": int(os.environ.get("POSTGRES_PORT", "5433")),
    "dbname": os.environ.get("POSTGRES_DB", "jarvis"),
    "user": os.environ.get("POSTGRES_USER", "jarvis"),
    "password": os.environ.get("POSTGRES_PASSWORD", "1903"),
}
EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")


class InterpretRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)


class InterpretResponse(BaseModel):
    status: str
    message: str
    text: str
    model: str
    action: dict[str, object] | None = None


class UserContext(BaseModel):
    name: str = Field(default=USER_NAME, max_length=100)
    preferences: list[str] = Field(default_factory=list, max_length=20)
    notes: list[str] = Field(default_factory=list, max_length=50)


class ContextState(BaseModel):
    profile: UserContext = Field(default_factory=UserContext)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=50)


def database() -> Connection:
    return connect(**DB_CONFIG)


def initialize_database() -> None:
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jarvis_profile (
                    profile_id SMALLINT PRIMARY KEY CHECK (profile_id = 1),
                    name TEXT NOT NULL,
                    preferences JSONB NOT NULL DEFAULT '[]',
                    notes JSONB NOT NULL DEFAULT '[]',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id BIGSERIAL PRIMARY KEY,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    model TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS chat_keywords (
                    id BIGSERIAL PRIMARY KEY,
                    message_id BIGINT NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
                    keyword TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE(message_id, keyword)
                );
                CREATE INDEX IF NOT EXISTS chat_keywords_keyword_idx ON chat_keywords(keyword);
                CREATE TABLE IF NOT EXISTS memories (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    content TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'conversation',
                    embedding JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    filename TEXT NOT NULL,
                    path TEXT,
                    mime_type TEXT,
                    content_hash TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE(document_id, chunk_index)
                );
            """)
            cursor.execute(
                """INSERT INTO jarvis_profile(profile_id, name)
                   VALUES (1, %s) ON CONFLICT (profile_id) DO NOTHING""",
                (USER_NAME,),
            )
        connection.commit()


def load_state() -> ContextState:
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT name, preferences, notes FROM jarvis_profile WHERE profile_id = 1")
            profile = cursor.fetchone()
            cursor.execute(
                """SELECT role, content FROM chat_messages
                   ORDER BY id DESC LIMIT 8"""
            )
            history = [
                {"role": row[0], "text": row[1]}
                for row in reversed(cursor.fetchall())
            ]
    if profile is None:
        return ContextState()
    return ContextState(
        profile=UserContext(name=profile[0], preferences=profile[1], notes=profile[2]),
        history=history,
    )


def save_profile(profile: UserContext) -> None:
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """UPDATE jarvis_profile
                   SET name = %s, preferences = %s::jsonb, notes = %s::jsonb, updated_at = now()
                   WHERE profile_id = 1""",
                (profile.name, json.dumps(profile.preferences), json.dumps(profile.notes)),
            )
        connection.commit()


def keywords(text: str) -> set[str]:
    ignored = {"this", "that", "with", "from", "what", "have", "your", "about", "please"}
    return {
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)
        if word.lower() not in ignored
    }


def save_message(role: str, text: str, model: str | None = None) -> None:
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO chat_messages(role, content, model) VALUES (%s, %s, %s) RETURNING id",
                (role, text, model),
            )
            message_id = cursor.fetchone()[0]
            for keyword in keywords(text):
                cursor.execute(
                    "INSERT INTO chat_keywords(message_id, keyword) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (message_id, keyword),
                )
        connection.commit()


def embed_text(text: str) -> list[float] | None:
    payload = json.dumps({"model": EMBED_MODEL, "input": text}).encode("utf-8")
    request = Request(
        f"{OLLAMA_URL}/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError):
        return None
    embeddings = result.get("embeddings", [])
    return embeddings[0] if embeddings else None


def desktop_request(path: str, payload: dict[str, str]) -> dict[str, object]:
    request = Request(
        f"{DESKTOP_AGENT_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError) as error:
        raise HTTPException(status_code=503, detail=f"Desktop agent is unavailable: {error}") from error


def desktop_action(text: str) -> tuple[str, dict[str, object]] | None:
    normalized = text.casefold().strip()
    if any(word in normalized for word in ("delete", "remove", "erase", "move", "rename")):
        return (
            "I will not perform destructive or modifying file actions from voice yet. "
            "Those operations need an explicit preview and confirmation.",
            {"status": "blocked", "reason": "confirmation_required"},
        )

    applications = {
        "vs code": "code",
        "visual studio code": "code",
        "code editor": "code",
        "firefox": "firefox",
        "browser": "firefox",
        "files": "nautilus",
        "file manager": "nautilus",
        "terminal": "gnome-terminal",
    }
    if re.search(r"\b(open|launch|start)\b", normalized):
        explicit_path = re.search(r"(?:open|launch)\s+(\/home\/teja\/[^\s]+)", normalized)
        if explicit_path:
            path = explicit_path.group(1).rstrip(".,")
            result = desktop_request("/open", {"path": path})
            return f"Opening {path}.", {"type": "open", **result}
        for name, executable in applications.items():
            if re.search(rf"\b(?:open|launch|start)\s+(?:the\s+)?{re.escape(name)}\b", normalized):
                result = desktop_request("/launch", {"executable": executable})
                return f"Launching {name}.", {"type": "launch", **result}

    search = re.search(r"\b(?:find|search for|look for)\s+(?:the\s+)?(.+?)(?:\s+files?)?$", normalized)
    if search:
        query = search.group(1).strip()
        if query:
            request = Request(
                f"{DESKTOP_AGENT_URL}/files?query={quote(query)}",
                headers={"Accept": "application/json"},
                method="GET",
            )
            try:
                with urlopen(request, timeout=10) as response:
                    result = json.load(response)
            except (HTTPError, URLError, TimeoutError) as error:
                raise HTTPException(status_code=503, detail=f"Desktop agent is unavailable: {error}") from error
            return f"I found {len(result)} matching file(s) for {query}.", {
                "type": "search",
                "query": query,
                "results": result,
            }
    return None


def save_memory(text: str, embedding: list[float] | None) -> None:
    with database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO memories(content, embedding) VALUES (%s, %s::jsonb)",
                (text, json.dumps(embedding) if embedding is not None else None),
            )
        connection.commit()


initialize_database()


def context_prompt(history: list[dict[str, str]], context: UserContext) -> str:
    recent = "\n".join(f"{item['role']}: {item['text']}" for item in history[-8:])
    return (
        f"User profile: {context.model_dump_json()}\n"
        "Use this profile and recent conversation for continuity. Do not invent "
        "personal facts. Ask when information is missing.\n"
        f"Recent conversation:\n{recent or '(none)'}"
    )


def ask_ollama(text: str, context: UserContext, history: list[dict[str, str]]) -> str:
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "system": (
            "You are JARVIS, a concise and helpful personal assistant running on "
            "Ubuntu Linux. Answer the user's request directly. Do not mention "
            "Apple, iPhone, or other unrelated platforms. Do not claim to have "
            "performed desktop actions; explain when an action needs the desktop "
            "agent. Keep normal answers under 240 words unless the user asks for "
            "a detailed explanation.\n\n"
            f"{context_prompt(history, context)}"
        ),
        "prompt": text,
        "stream": False,
        "options": {
            "num_predict": 320,
            "temperature": 0.3,
        },
    }).encode("utf-8")
    request = Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError) as error:
        raise HTTPException(
            status_code=503,
            detail=f"Ollama is unavailable: {error}",
        ) from error

    answer = result.get("response", "").strip()
    if not answer:
        raise HTTPException(status_code=502, detail="Ollama returned an empty response")
    return answer


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "jarvis-ai-service",
        "provider": "ollama",
        "model": OLLAMA_MODEL,
    }


@app.get("/context", response_model=UserContext)
def get_context() -> UserContext:
    with CONTEXT_LOCK:
        return load_state().profile


@app.put("/context", response_model=UserContext)
def update_context(context: UserContext) -> UserContext:
    with CONTEXT_LOCK:
        save_profile(context)
        return context


@app.post("/interpret")
def interpret(request: InterpretRequest) -> InterpretResponse:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text must not be blank")
    with CONTEXT_LOCK:
        state = load_state()
        history = state.history
        action = desktop_action(text)
        if action is None:
            answer = ask_ollama(text, state.profile, history)
            action_result = None
        else:
            answer, action_result = action
        save_message("user", text)
        save_memory(text, embed_text(text))
        save_message("assistant", answer, OLLAMA_MODEL)
    return {
        "status": "ok",
        "message": answer,
        "text": text,
        "model": OLLAMA_MODEL,
        "action": action_result,
    }
