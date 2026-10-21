import os
import subprocess
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

app = FastAPI(title="JARVIS Desktop Agent", version="0.1.0")


def allowed_roots() -> tuple[Path, ...]:
    raw = os.environ.get("JARVIS_ALLOWED_ROOTS", str(Path.home() / "Downloads"))
    roots = tuple(Path(value).expanduser().resolve() for value in raw.split(":") if value)
    if not roots:
        raise RuntimeError("JARVIS_ALLOWED_ROOTS must contain at least one directory")
    return roots


def safe_path(value: str) -> Path:
    candidate = Path(value).expanduser().resolve()
    if not any(candidate == root or root in candidate.parents for root in allowed_roots()):
        raise HTTPException(status_code=403, detail="path is outside allowed roots")
    return candidate


class OpenRequest(BaseModel):
    path: str = Field(min_length=1)


class LaunchRequest(BaseModel):
    executable: str = Field(pattern=r"^[a-zA-Z0-9._+-]+$")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "jarvis-desktop-agent"}


@app.get("/files")
def search_files(
    query: Annotated[str, Query(min_length=1, max_length=100)],
    root: str | None = None,
) -> list[dict[str, str | int]]:
    base = safe_path(root) if root else allowed_roots()[0]
    if not base.is_dir():
        raise HTTPException(status_code=404, detail="search root does not exist")
    results: list[dict[str, str | int]] = []
    for path in base.rglob("*"):
        if len(results) >= 100:
            break
        if query.casefold() in path.name.casefold():
            try:
                stat = path.stat()
            except OSError:
                continue
            results.append({"path": str(path), "name": path.name, "size": stat.st_size})
    return results


@app.post("/open")
def open_path(request: OpenRequest) -> dict[str, str]:
    path = safe_path(request.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="path does not exist")
    subprocess.Popen(["gio", "open", str(path)], start_new_session=True)
    return {"status": "started", "path": str(path)}


@app.post("/launch")
def launch_application(request: LaunchRequest) -> dict[str, str]:
    allowed = {"code", "firefox", "nautilus", "gnome-terminal"}
    if request.executable not in allowed:
        raise HTTPException(status_code=403, detail="application is not allowed")
    subprocess.Popen([request.executable], start_new_session=True)
    return {"status": "started", "application": request.executable}
