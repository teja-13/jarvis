"use client";

import { FormEvent, useState } from "react";

type Message = { role: "user" | "jarvis"; text: string };
type RecognitionEvent = { results: { [index: number]: { [index: number]: { transcript: string } } } };
type Recognition = {
  lang: string;
  interimResults: boolean;
  onresult: (event: RecognitionEvent) => void;
  onerror: () => void;
  onend: () => void;
  start: () => void;
  stop: () => void;
};
type RecognitionConstructor = new () => Recognition;
type ViewMode = "text" | "voice";

export default function Home() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [state, setState] = useState("idle");
  const [listening, setListening] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode>("text");
  const [lastResponse, setLastResponse] = useState("");

  function speak(text: string) {
    if (voiceEnabled && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      const maleVoice = window.speechSynthesis.getVoices().find((voice) =>
        /male|david|guy|daniel|alex|fred|james|jorge|rishi/i.test(voice.name),
      );
      if (maleVoice) utterance.voice = maleVoice;
      utterance.rate = 0.95;
      utterance.pitch = 0.85;
      utterance.onstart = () => setState("speaking");
      utterance.onend = () => setState("idle");
      window.speechSynthesis.speak(utterance);
    }
  }

  async function sendText(text: string) {
    if (!text) return;
    setMessages((current) => [...current, { role: "user", text }]);
    setInput("");
    setState("processing");
    try {
      const response = await fetch("http://localhost:8000/interpret", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? "AI service request failed");
      const answer = result.message as string;
      setLastResponse(answer);
      setMessages((current) => [
        ...current,
        { role: "jarvis", text: answer },
      ]);
      speak(answer);
    } catch (error) {
      const message = error instanceof TypeError
        ? "I could not reach the AI service. Make sure it is running on http://localhost:8000."
        : error instanceof Error ? error.message : "The AI service is unavailable.";
      setMessages((current) => [...current, { role: "jarvis", text: message }]);
      speak(message);
    } finally {
      setState("idle");
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void sendText(input.trim());
  }

  function toggleListening() {
    const Recognition = (window as Window & { SpeechRecognition?: RecognitionConstructor; webkitSpeechRecognition?: RecognitionConstructor }).SpeechRecognition
      ?? (window as Window & { webkitSpeechRecognition?: RecognitionConstructor }).webkitSpeechRecognition;
    if (!Recognition) {
      setMessages((current) => [...current, { role: "jarvis", text: "Voice input is not supported by this browser. You can still type requests." }]);
      return;
    }
    if (listening) return;
    const recognition = new Recognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const text = event.results[0][0].transcript.trim();
      setInput(text);
      void sendText(text);
    };
    recognition.onerror = () => {
      setMessages((current) => [...current, { role: "jarvis", text: "I could not access the microphone. Check browser microphone permissions." }]);
      setListening(false);
    };
    recognition.onend = () => setListening(false);
    setListening(true);
    setState("listening");
    recognition.start();
  }

  function voiceScreen() {
    return (
      <main className="voice-screen">
        <header className="voice-header">
          <button className="minimal-button" type="button" onClick={() => setViewMode("text")}>TEXT MODE</button>
          <div className="voice-brand"><span className="voice-dot" /> JARVIS</div>
          <span className="status orange-status">{state === "speaking" ? "SPEAKING" : state === "processing" ? "THINKING" : listening ? "LISTENING" : "READY"}</span>
        </header>
        <section className={`voice-core ${state} ${listening ? "listening" : ""}`} aria-label="JARVIS voice visualizer">
          <div className="core-rings"><span /><span /><span /></div>
          <div className="core-center"><span className="core-pulse" /><b>JARVIS</b></div>
        </section>
        <p className="voice-prompt">{state === "speaking" ? "JARVIS is speaking" : state === "processing" ? "Processing your request" : listening ? "Listening to you" : "Press the microphone to speak"}</p>
        {lastResponse && <p className="voice-response">{lastResponse}</p>}
        <div className="voice-controls">
          <button className={`mic-button ${listening ? "active" : ""}`} type="button" onClick={toggleListening} aria-label="Start voice input"><span>{listening ? "●" : "⌕"}</span></button>
          <button className="voice-mute" type="button" onClick={() => setVoiceEnabled((enabled) => !enabled)}>{voiceEnabled ? "SOUND ON" : "SOUND OFF"}</button>
        </div>
      </main>
    );
  }

  if (viewMode === "voice") return voiceScreen();

  return (
    <main className="shell">
      <header><div><p className="eyebrow">LOCAL COMMAND CENTER</p><h1>JARVIS</h1></div><div className="header-actions"><button className="mode-button" type="button" onClick={() => setViewMode("voice")}>VOICE MODE</button><span className={`status ${state}`}>{state.toUpperCase()}</span></div></header>
      <section className="orb-panel"><div className={`orb ${state} ${listening ? "listening" : ""}`}><span /></div><p>{listening ? "Listening..." : "Systems nominal · local mode"}</p></section>
      <section className="conversation" aria-live="polite">
        {messages.length === 0 && <p className="empty">Good evening. Ask JARVIS by voice or text.</p>}
        {messages.map((message, index) => <article className={message.role} key={`${message.role}-${index}`}><b>{message.role === "user" ? "YOU" : "JARVIS"}</b><p>{message.text}</p></article>)}
      </section>
      <form onSubmit={submit}><input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask JARVIS something..." aria-label="Message JARVIS" /><button type="button" onClick={() => { setViewMode("voice"); toggleListening(); }} aria-label="Use microphone">{listening ? "LISTENING" : "MIC"}</button><button type="submit">SEND</button></form>
      <button className="voice-toggle" type="button" onClick={() => setVoiceEnabled((enabled) => !enabled)}>{voiceEnabled ? "VOICE OUTPUT ON" : "VOICE OUTPUT OFF"}</button>
      <nav><span>MEMORIES</span><span>FILES</span><span>TASKS</span><span>SETTINGS</span></nav>
    </main>
  );
}
