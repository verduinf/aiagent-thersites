"""
Scaffolding Script for Standalone AI Chatbot (C:\Dev\ai-chatbot)
Pure conversational speed: ZERO reasoning overhead, NO inner loops, direct token streaming.
"""
import os
import shutil
from pathlib import Path

DEST_DIR = Path(r"C:\Dev\ai-chatbot")
SRC_DIR = Path(r"C:\Dev\aiagent-thersites")

def setup_directories():
    for sub in [".agents", "core", "models", "static", "data"]:
        (DEST_DIR / sub).mkdir(parents=True, exist_ok=True)
    print(f"[OK] Directory structure verified at {DEST_DIR}")

def copy_agents_roster():
    src_agents = SRC_DIR / ".agents"
    dest_agents = DEST_DIR / ".agents"
    if src_agents.exists():
        skills_src = src_agents / "skills"
        skills_dest = dest_agents / "skills"
        if skills_src.exists():
            shutil.copytree(skills_src, skills_dest, dirs_exist_ok=True)
        print("[OK] .agents skills copied")
    
    agents_md = """# Workspace Behavioral Rules & Guidelines — AI Chatbot

## Core Philosophy
This repository houses **Local AI Chatbot**: a lightning-fast, locally-hosted conversational assistant powered by `qwen3.5-9b` running via Ollama on the Aether laptop.

### Operating Principles
* **ZERO REASONING OVERHEAD**: Pure, direct token streaming without chain-of-thought or thinking budget delays.
* **NO TOOLS / NO INNER LOOPS**: Straightforward conversational turn progression with persistent chat history.
* **PORT**: Dedicated to **Port 8080** (concurrent with Thersites on 8000).

---

## Divine Engineering Roster

0. **Helios (`lead-system-engineer-and-orchestrator`)**: Titan God of the Sun. System momentum and architecture.
1. **Argus (`test-suite-guardian-and-qa-lead`)**: QA lead ensuring streaming stability and database integrity.
2. **Athena (`code-peer-review-and-architect`)**: Architect overseeing performance, schema cleanliness, and responsiveness.
"""
    with open(dest_agents / "AGENTS.md", "w", encoding="utf-8") as f:
        f.write(agents_md)
    print("[OK] AGENTS.md written")

def create_config_files():
    config_json = """{
  "PORT": 8080,
  "OLLAMA_BASE_URL": "http://localhost:11434",
  "MODEL_NAME": "qwen3.5:9b",
  "AVAILABLE_MODELS": [
    "qwen3.5:9b",
    "granite4.2:8b",
    "ornith-1.5:9b",
    "qwen3.5:4b"
  ],
  "KEEP_AI_ALIVE": "5m",
  "NUM_CTX": 16384,
  "NUM_GPU": 58,
  "ROLLING_BUFFER_CHAR_LIMIT": 24000,
  "AI_TEMPERATURE": 0.5,
  "SYSTEM_PROMPT": "You are a helpful, intelligent, and articulate local AI assistant. Provide clear, direct, and concise answers using clean Markdown formatting and syntax-highlighted code blocks."
}
"""
    with open(DEST_DIR / "config.json", "w", encoding="utf-8") as f:
        f.write(config_json)

    config_py = '''"""
Configuration Loader for Standalone AI Chatbot (Zero Reasoning / Direct Stream)
"""
import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    try:
        with open(ENV_PATH, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip(\'"\').strip("\'")
                    if k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass

CONFIG_JSON_PATH = BASE_DIR / "config.json"
config_data = {}
if CONFIG_JSON_PATH.exists():
    try:
        with open(CONFIG_JSON_PATH, "r", encoding="utf-8-sig") as f:
            config_data = json.load(f)
    except Exception as e:
        print(f"Warning: Failed to parse config.json: {e}")

PORT = int(os.environ.get("PORT", config_data.get("PORT", 8080)))
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", config_data.get("OLLAMA_BASE_URL", "http://localhost:11434"))
MODEL_NAME = os.environ.get("MODEL_NAME", config_data.get("MODEL_NAME", "qwen3.5:9b"))
AVAILABLE_MODELS = config_data.get("AVAILABLE_MODELS", ["qwen3.5:9b", "granite4.2:8b", "ornith-1.5:9b", "qwen3.5:4b"])
KEEP_AI_ALIVE = os.environ.get("KEEP_AI_ALIVE", config_data.get("KEEP_AI_ALIVE", "5m"))
NUM_CTX = int(config_data.get("NUM_CTX", 16384))
NUM_GPU = int(config_data.get("NUM_GPU", 58))
ROLLING_BUFFER_CHAR_LIMIT = int(config_data.get("ROLLING_BUFFER_CHAR_LIMIT", 24000))
AI_TEMPERATURE = float(config_data.get("AI_TEMPERATURE", 0.5))
SYSTEM_PROMPT = config_data.get(
    "SYSTEM_PROMPT",
    "You are a helpful, intelligent, and articulate local AI assistant. Provide clear, direct, and concise answers using clean Markdown formatting."
)

STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "chat.db"
'''
    with open(DEST_DIR / "config.py", "w", encoding="utf-8") as f:
        f.write(config_py)
    print("[OK] config.json and config.py written")

def create_models_files():
    (DEST_DIR / "models" / "__init__.py").write_text("", encoding="utf-8")

    context_py = '''"""
Context calculations for multi-model runtime (dynamic token estimation).
"""
from typing import Dict, Any, List
from config import NUM_CTX

def estimate_dynamic_context(messages: List[Dict[str, str]], floor: int = 2048, headroom: int = 1024) -> int:
    """Estimates dynamic context size based on total characters with headroom."""
    total_chars = sum(len(m.get("content", "")) for m in messages)
    estimated_tokens = int(total_chars / 3.2) + 200
    return min(NUM_CTX, max(floor, estimated_tokens + headroom))
'''
    with open(DEST_DIR / "models" / "context.py", "w", encoding="utf-8") as f:
        f.write(context_py)

    ollama_client_py = '''"""
Ollama HTTP API Client with direct streaming token generator.
Enforces zero reasoning overhead for ultra-low latency.
"""
import time
import json
import requests
from typing import Dict, Any, List, Generator
from config import OLLAMA_BASE_URL, MODEL_NAME, KEEP_AI_ALIVE, NUM_GPU, AI_TEMPERATURE
from models.context import estimate_dynamic_context

_SESSION = requests.Session()

def prewarm_ollama_model(model: str = MODEL_NAME) -> bool:
    """Pre-warms the model into VRAM during server startup."""
    url = f"{OLLAMA_BASE_URL.rstrip(\'/\')}/api/chat"
    payload = {
        "model": model,
        "messages": [],
        "keep_alive": KEEP_AI_ALIVE,
        "think": False,
        "options": {"num_ctx": 2048, "num_thread": 8},
        "stream": False
    }
    try:
        resp = _SESSION.post(url, json=payload, timeout=60)
        return resp.status_code == 200
    except Exception as e:
        print(f"[Ollama] Pre-warm notice: {e}")
        return False

def stream_ollama_chat(
    messages: List[Dict[str, str]],
    model: str = MODEL_NAME
) -> Generator[Dict[str, Any], None, None]:
    """
    Streams tokens directly from Ollama via line-delimited JSON chunks.
    No reasoning tags, no CoT delay.
    """
    url = f"{OLLAMA_BASE_URL.rstrip(\'/\')}/api/chat"
    dynamic_num_ctx = estimate_dynamic_context(messages)
    is_granite = "granite" in model.lower()

    payload = {
        "model": model,
        "messages": messages,
        "keep_alive": KEEP_AI_ALIVE,
        "think": False,
        "options": {
            "num_ctx": dynamic_num_ctx,
            "num_gpu": NUM_GPU,
            "num_predict": 2048,
            "num_thread": 8,
            "temperature": AI_TEMPERATURE
        },
        "stream": True
    }
    if is_granite:
        payload["options"]["reasoning_effort"] = "none"

    start_time = time.time()
    try:
        with _SESSION.post(url, json=payload, stream=True, timeout=300) as response:
            if response.status_code != 200:
                yield {"type": "error", "message": f"Ollama HTTP error {response.status_code}: {response.text}"}
                return

            total_tokens = 0
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8"))
                except Exception:
                    continue

                msg = chunk.get("message", {})
                content = msg.get("content", "")
                
                # Filter any unexpected residual <think> blocks if present
                if "<think>" in content:
                    content = content.replace("<think>", "")
                if "</think>" in content:
                    content = content.replace("</think>", "")

                if content:
                    total_tokens += 1
                    yield {"type": "token", "chunk": content}

                if chunk.get("done", False):
                    wall_time = time.time() - start_time
                    eval_count = chunk.get("eval_count", total_tokens)
                    eval_dur_ns = chunk.get("eval_duration", 0)
                    tok_per_sec = (eval_count / eval_dur_ns * 1e9) if eval_dur_ns > 0 else (eval_count / wall_time if wall_time > 0 else 0)
                    yield {
                        "type": "done",
                        "tok_per_sec": round(tok_per_sec, 1),
                        "latency_sec": round(wall_time, 2),
                        "eval_count": eval_count
                    }
                    return

    except Exception as e:
        yield {"type": "error", "message": f"Streaming failure: {str(e)}"}
'''
    with open(DEST_DIR / "models" / "ollama_client.py", "w", encoding="utf-8") as f:
        f.write(ollama_client_py)
    print("[OK] models/ files written (zero reasoning)")

def create_core_files():
    (DEST_DIR / "core" / "__init__.py").write_text("", encoding="utf-8")

    database_py = '''"""
SQLite Database Operations for AI Chatbot (data/chat.db).
Manages chat sessions, messages, and rolling conversation history.
"""
import sqlite3
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
from config import DB_PATH

@contextmanager
def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Initializes sessions and messages tables."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT DEFAULT 'New Chat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                sequence_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tok_per_sec REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        """)

def create_session(session_id: Optional[str] = None, title: Optional[str] = None) -> Dict[str, Any]:
    import uuid
    sid = session_id or f"sess_{uuid.uuid4().hex[:8]}"
    stitle = title or "New Chat"
    with get_db_connection() as conn:
        conn.execute("UPDATE sessions SET is_active = 0")
        conn.execute(
            "INSERT INTO sessions (id, title, is_active) VALUES (?, ?, 1)",
            (sid, stitle)
        )
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
        return dict(row)

def set_active_session(session_id: str) -> Dict[str, Any]:
    with get_db_connection() as conn:
        conn.execute("UPDATE sessions SET is_active = 0")
        conn.execute("UPDATE sessions SET is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return create_session(session_id)
        return dict(row)

def get_or_create_active_session() -> Dict[str, Any]:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE is_active = 1 ORDER BY updated_at DESC LIMIT 1").fetchone()
        if row:
            return dict(row)
        latest = conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC LIMIT 1").fetchone()
        if latest:
            conn.execute("UPDATE sessions SET is_active = 1 WHERE id = ?", (latest["id"],))
            return dict(latest)
    return create_session()

def get_recent_sessions(limit: int = 50) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

def update_session_title(session_id: str, new_title: str) -> bool:
    with get_db_connection() as conn:
        res = conn.execute("UPDATE sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_title, session_id))
        return res.rowcount > 0

def delete_session(session_id: str) -> bool:
    with get_db_connection() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        res = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return res.rowcount > 0

def add_message(session_id: str, role: str, content: str, tok_per_sec: float = 0.0) -> Dict[str, Any]:
    with get_db_connection() as conn:
        last = conn.execute(
            "SELECT MAX(sequence_id) as max_seq FROM messages WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        next_seq = (last["max_seq"] or 0) + 1
        
        cursor = conn.execute(
            """INSERT INTO messages (session_id, sequence_id, role, content, tok_per_sec)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, next_seq, role, content, tok_per_sec)
        )
        conn.execute("UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
        
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)

def get_all_messages(session_id: str) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY sequence_id ASC",
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_rolling_messages(session_id: str, char_limit: int = 24000) -> List[Dict[str, str]]:
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY sequence_id DESC",
            (session_id,)
        ).fetchall()
        
    collected = []
    current_chars = 0
    for r in rows:
        c = r["content"] or ""
        if current_chars + len(c) > char_limit and collected:
            break
        collected.append({"role": r["role"], "content": c})
        current_chars += len(c)
        
    collected.reverse()
    return collected
'''
    with open(DEST_DIR / "core" / "database.py", "w", encoding="utf-8") as f:
        f.write(database_py)

    engine_py = '''"""
Streaming Conversation Engine for AI Chatbot (Direct response, zero reasoning).
"""
from typing import Generator, Dict, Any, Optional
from config import MODEL_NAME, SYSTEM_PROMPT, ROLLING_BUFFER_CHAR_LIMIT
from core.database import (
    add_message, get_rolling_messages, get_all_messages, update_session_title
)
from models.ollama_client import stream_ollama_chat

def run_chat_stream(
    session_id: str,
    user_prompt: str,
    model_name: Optional[str] = None
) -> Generator[Dict[str, Any], None, None]:
    """
    Executes pure streaming chat conversation with zero reasoning overhead.
    """
    effective_model = model_name or MODEL_NAME
    
    # 1. Store user prompt
    add_message(session_id, "user", user_prompt)
    
    # Auto-generate friendly title if this is the very first exchange
    existing_messages = get_all_messages(session_id)
    if len(existing_messages) <= 2:
        clean_title = user_prompt.strip().split("\\n")[0][:36]
        if len(user_prompt.strip()) > 36:
            clean_title += "..."
        update_session_title(session_id, clean_title)
        yield {"type": "session_title", "title": clean_title}

    # 2. Build conversation context
    rolling = get_rolling_messages(session_id, char_limit=ROLLING_BUFFER_CHAR_LIMIT)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + rolling
    
    yield {"type": "start", "model": effective_model}

    assistant_content = []
    tok_per_sec = 0.0

    # 3. Stream direct tokens from Ollama
    for chunk in stream_ollama_chat(messages, model=effective_model):
        c_type = chunk.get("type")
        if c_type == "token":
            t = chunk.get("chunk", "")
            assistant_content.append(t)
            yield chunk
        elif c_type == "done":
            tok_per_sec = chunk.get("tok_per_sec", 0.0)
            yield chunk
        elif c_type == "error":
            yield chunk
            return

    # 4. Persist completed assistant response
    full_text = "".join(assistant_content)
    add_message(session_id, "assistant", full_text, tok_per_sec=tok_per_sec)
'''
    with open(DEST_DIR / "core" / "engine.py", "w", encoding="utf-8") as f:
        f.write(engine_py)
    print("[OK] core/ files written (direct stream)")

def create_server_files():
    server_py = '''"""
FastAPI Server & SSE API Endpoints for Standalone AI Chatbot
Dedicated to Port 8080 (Zero reasoning / Direct stream).
"""
import os
import json
import asyncio
import subprocess
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import PORT, STATIC_DIR, MODEL_NAME, AVAILABLE_MODELS
from core.database import (
    init_db, create_session, set_active_session, get_recent_sessions,
    get_or_create_active_session, add_message, get_all_messages,
    delete_session, update_session_title
)
from core.engine import run_chat_stream
from models.ollama_client import prewarm_ollama_model

def kill_existing_port_process(port: int = PORT):
    """Kills any lingering process on the designated port."""
    try:
        cmd = f\'netstat -ano | findstr LISTENING | findstr :{port}\'
        output = subprocess.check_output(cmd, shell=True, text=True, errors=\'ignore\')
        current_pid = str(os.getpid())
        for line in output.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5:
                pid = parts[-1]
                if pid.isdigit() and pid != current_pid:
                    print(f"Terminating old server process (PID {pid}) listening on port {port}...")
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(asyncio.to_thread(prewarm_ollama_model))
    yield

app = FastAPI(title="AI Chatbot", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

@app.get("/api/models")
async def get_models():
    return {"models": AVAILABLE_MODELS, "default": MODEL_NAME}

@app.get("/api/sessions")
async def list_sessions():
    active_sess = get_or_create_active_session()
    sessions = get_recent_sessions()
    return {"sessions": sessions, "active_session_id": active_sess["id"]}

@app.post("/api/sessions")
async def create_new_session(title: Optional[str] = None):
    return create_session(title=title)

@app.post("/api/sessions/{session_id}/activate")
async def activate_session(session_id: str):
    return set_active_session(session_id)

@app.delete("/api/sessions/{session_id}")
async def remove_session(session_id: str):
    deleted = delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "success", "session_id": session_id}

class RenamePayload(BaseModel):
    title: str

@app.put("/api/sessions/{session_id}/title")
async def rename_session(session_id: str, payload: RenamePayload):
    updated = update_session_title(session_id, payload.title)
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "success", "title": payload.title}

@app.get("/api/messages")
async def list_messages(session_id: Optional[str] = None):
    if not session_id:
        active_sess = get_or_create_active_session()
        session_id = active_sess["id"]
    return get_all_messages(session_id)

@app.get("/api/chat/stream")
async def stream_chat(
    prompt: str,
    session_id: Optional[str] = None,
    model: Optional[str] = None
):
    if not session_id:
        active_sess = get_or_create_active_session()
        session_id = active_sess["id"]
    set_active_session(session_id)

    async def event_generator():
        for chunk in run_chat_stream(session_id, prompt, model_name=model):
            yield f"data: {json.dumps(chunk)}\\n\\n"
            await asyncio.sleep(0.005)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    kill_existing_port_process(port=PORT)
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=PORT, reload=True)
'''
    with open(DEST_DIR / "server.py", "w", encoding="utf-8") as f:
        f.write(server_py)

    run_server_cmd = f'''@echo off
title AI Chatbot [Port 8080]
echo ========================================================
echo   Starting AI Chatbot on http://127.0.0.1:8080
echo ========================================================
cd /d "%~dp0"

start http://127.0.0.1:8080
python server.py
pause
'''
    with open(DEST_DIR / "run_server.cmd", "w", encoding="utf-8") as f:
        f.write(run_server_cmd)
    print("[OK] server.py and run_server.cmd written")

def create_frontend_files():
    index_html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Chatbot — Fast Local LLM</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>&#128172;</text></svg>">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <!-- Marked for Markdown rendering & Highlight.js for code formatting -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <link rel="stylesheet" href="/static/style.css?v=2">
</head>
<body>
    <div class="app-container">
        <!-- Left Sidebar: Sessions -->
        <aside class="sidebar">
            <div class="sidebar-header">
                <div class="brand">
                    <span class="brand-icon">&#128172;</span>
                    <span class="brand-title">AI Chatbot</span>
                </div>
                <button id="newChatBtn" class="btn btn-new-chat" title="New Conversation (Ctrl+N)">
                    <span>+ New Chat</span>
                </button>
            </div>

            <div class="sessions-scroll" id="sessionsList">
                <!-- Dynamically loaded chat sessions -->
            </div>

            <div class="sidebar-footer">
                <div class="model-pill">
                    <span class="pulse-dot"></span>
                    <span id="sidebarModelName">qwen3.5:9b</span>
                </div>
                <div class="port-tag">Port 8080</div>
            </div>
        </aside>

        <!-- Main Chat Surface -->
        <main class="chat-viewport">
            <header class="topbar">
                <div class="topbar-left">
                    <div class="model-selector-box" title="Select Local Model">
                        <span class="control-label">&#9881;&#65039; Model:</span>
                        <select id="modelSelect" class="styled-select"></select>
                    </div>
                </div>

                <div class="topbar-right">
                    <div class="perf-tag" id="perfTag">⚡ -- tok/s</div>
                </div>
            </header>

            <section class="messages-container" id="messagesContainer">
                <div class="empty-state" id="emptyState">
                    <div class="empty-icon">&#129302;</div>
                    <h2>How can I help you today?</h2>
                    <p>Direct local responses. Fast, private, and zero cloud dependencies.</p>
                    <div class="suggestion-chips">
                        <button class="chip" onclick="usePrompt('Explain how quantum entanglement works simply.')">💡 Quantum physics simply</button>
                        <button class="chip" onclick="usePrompt('Write a Python function to compute moving averages.')">🐍 Python moving average</button>
                        <button class="chip" onclick="usePrompt('Draft a concise professional project status email.')">✉️ Status update email</button>
                    </div>
                </div>
            </section>

            <footer class="input-container">
                <form id="chatForm" class="input-dock">
                    <textarea 
                        id="promptInput" 
                        placeholder="Type a message... (Press Enter to send, Shift+Enter for newline)"
                        rows="1"
                    ></textarea>
                    <div class="dock-actions">
                        <button type="submit" id="sendBtn" class="btn btn-send" title="Send message">
                            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                <line x1="22" y1="2" x2="11" y2="13"></line>
                                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                            </svg>
                        </button>
                    </div>
                </form>
            </footer>
        </main>
    </div>

    <script src="/static/app.js?v=2"></script>
</body>
</html>
'''
    with open(DEST_DIR / "static" / "index.html", "w", encoding="utf-8") as f:
        f.write(index_html)

    style_css = '''/* AI Chatbot — Clean Dark Theme (Zero Reasoning Overhead) */
:root {
    --bg-main: #0b0f19;
    --bg-card: #111827;
    --bg-sidebar: #070a12;
    --bg-input: #151d30;
    --bg-code: #0b0e17;
    
    --border-color: rgba(255, 255, 255, 0.08);
    --border-hover: rgba(56, 189, 248, 0.3);
    
    --primary: #38bdf8;
    --primary-gradient: linear-gradient(135deg, #38bdf8, #818cf8);
    --user-bubble: linear-gradient(135deg, #1e293b, #273549);
    
    --text-main: #f1f5f9;
    --text-muted: #94a3b8;
    --text-dim: #64748b;
    
    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 16px;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background-color: var(--bg-main);
    color: var(--text-main);
    height: 100vh;
    overflow: hidden;
}

.app-container {
    display: flex;
    height: 100vh;
    width: 100vw;
}

/* Sidebar */
.sidebar {
    width: 270px;
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
}

.sidebar-header {
    padding: 16px;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.brand {
    display: flex;
    align-items: center;
    gap: 10px;
}

.brand-icon {
    font-size: 1.4rem;
}

.brand-title {
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    background: var(--primary-gradient);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.btn-new-chat {
    width: 100%;
    padding: 10px 14px;
    background: rgba(56, 189, 248, 0.1);
    border: 1px solid rgba(56, 189, 248, 0.3);
    color: var(--primary);
    border-radius: var(--radius-md);
    font-weight: 600;
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
}

.btn-new-chat:hover {
    background: rgba(56, 189, 248, 0.2);
    border-color: var(--primary);
    transform: translateY(-1px);
}

.sessions-scroll {
    flex: 1;
    overflow-y: auto;
    padding: 10px 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.session-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 0.86rem;
    cursor: pointer;
    transition: all 0.15s ease;
    border: 1px solid transparent;
}

.session-item:hover {
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-main);
}

.session-item.active {
    background: rgba(56, 189, 248, 0.12);
    color: var(--primary);
    border-color: rgba(56, 189, 248, 0.25);
    font-weight: 500;
}

.session-title-text {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
}

.session-delete-btn {
    opacity: 0;
    background: transparent;
    border: none;
    color: var(--text-dim);
    cursor: pointer;
    font-size: 0.9rem;
    padding: 2px 6px;
    border-radius: 4px;
    transition: all 0.2s;
}

.session-item:hover .session-delete-btn {
    opacity: 1;
}

.session-delete-btn:hover {
    color: #f87171;
    background: rgba(248, 113, 113, 0.15);
}

.sidebar-footer {
    padding: 14px 16px;
    border-top: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 0.8rem;
}

.model-pill {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
}

.pulse-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #34d399;
    box-shadow: 0 0 8px #34d399;
}

.port-tag {
    color: var(--text-dim);
    font-size: 0.75rem;
    background: rgba(255, 255, 255, 0.05);
    padding: 2px 6px;
    border-radius: 4px;
}

/* Main Viewport */
.chat-viewport {
    flex: 1;
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: var(--bg-main);
    position: relative;
}

/* Topbar */
.topbar {
    height: 56px;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 24px;
    background: rgba(11, 15, 25, 0.8);
    backdrop-filter: blur(12px);
    z-index: 10;
}

.topbar-left {
    display: flex;
    align-items: center;
    gap: 16px;
}

.control-label {
    font-size: 0.82rem;
    color: var(--text-muted);
    font-weight: 500;
}

.styled-select {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    color: var(--text-main);
    padding: 6px 10px;
    border-radius: var(--radius-sm);
    font-size: 0.85rem;
    cursor: pointer;
    outline: none;
    font-family: 'JetBrains Mono', monospace;
}

.styled-select:focus {
    border-color: var(--primary);
}

.perf-tag {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    color: var(--primary);
    background: rgba(56, 189, 248, 0.08);
    border: 1px solid rgba(56, 189, 248, 0.2);
    padding: 4px 10px;
    border-radius: var(--radius-sm);
}

/* Messages Feed */
.messages-container {
    flex: 1;
    overflow-y: auto;
    padding: 24px 15%;
    display: flex;
    flex-direction: column;
    gap: 20px;
    scroll-behavior: smooth;
}

.empty-state {
    margin: auto;
    text-align: center;
    max-width: 500px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
}

.empty-icon {
    font-size: 3rem;
    margin-bottom: 8px;
}

.empty-state h2 {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-main);
}

.empty-state p {
    color: var(--text-muted);
    font-size: 0.9rem;
    line-height: 1.5;
}

.suggestion-chips {
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: 100%;
    margin-top: 16px;
}

.chip {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    color: var(--text-main);
    padding: 10px 14px;
    border-radius: var(--radius-md);
    cursor: pointer;
    font-size: 0.85rem;
    text-align: left;
    transition: all 0.2s;
}

.chip:hover {
    border-color: var(--primary);
    background: rgba(56, 189, 248, 0.05);
}

/* Message Bubbles */
.message-row {
    display: flex;
    width: 100%;
}

.message-row.user {
    justify-content: flex-end;
}

.message-row.assistant {
    justify-content: flex-start;
}

.user-bubble {
    background: var(--user-bubble);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: var(--text-main);
    padding: 12px 18px;
    border-radius: var(--radius-lg) var(--radius-lg) 4px var(--radius-lg);
    max-width: 80%;
    font-size: 0.95rem;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
}

.assistant-payload {
    display: flex;
    gap: 14px;
    max-width: 90%;
    width: 100%;
}

.assistant-avatar {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: var(--primary-gradient);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1rem;
    flex-shrink: 0;
    box-shadow: 0 0 10px rgba(56, 189, 248, 0.3);
}

.assistant-body {
    flex: 1;
    overflow-x: hidden;
}

/* Markdown formatting inside assistant messages */
.prose {
    font-size: 0.95rem;
    line-height: 1.6;
    color: var(--text-main);
    word-break: break-word;
}

.prose p {
    margin-bottom: 12px;
}

.prose p:last-child {
    margin-bottom: 0;
}

.prose h1, .prose h2, .prose h3 {
    margin-top: 16px;
    margin-bottom: 8px;
    color: #fff;
    font-weight: 600;
}

.prose ul, .prose ol {
    margin-left: 20px;
    margin-bottom: 12px;
}

.prose li {
    margin-bottom: 4px;
}

.prose code:not(pre code) {
    background: rgba(255, 255, 255, 0.08);
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85em;
    color: #38bdf8;
}

.code-block-wrapper {
    position: relative;
    margin: 14px 0;
    border-radius: var(--radius-md);
    overflow: hidden;
    border: 1px solid var(--border-color);
    background: var(--bg-code);
}

.code-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 12px;
    background: rgba(255, 255, 255, 0.03);
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: var(--text-dim);
}

.copy-btn {
    background: transparent;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 0.75rem;
    padding: 2px 6px;
    border-radius: 4px;
    transition: all 0.2s;
}

.copy-btn:hover {
    color: var(--text-main);
    background: rgba(255, 255, 255, 0.1);
}

.code-block-wrapper pre {
    margin: 0;
    padding: 14px;
    overflow-x: auto;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.88rem;
    line-height: 1.45;
}

/* Typing cursor indicator */
.typing-cursor {
    display: inline-block;
    width: 6px;
    height: 16px;
    background: var(--primary);
    margin-left: 4px;
    vertical-align: middle;
    animation: blink 0.8s infinite;
}

@keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
}

/* Input Area */
.input-container {
    padding: 16px 15% 24px;
    background: linear-gradient(180deg, transparent, var(--bg-main) 30%);
}

.input-dock {
    display: flex;
    align-items: flex-end;
    background: var(--bg-input);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: 10px 14px;
    gap: 10px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
    transition: border-color 0.2s;
}

.input-dock:focus-within {
    border-color: rgba(56, 189, 248, 0.5);
    box-shadow: 0 8px 30px rgba(56, 189, 248, 0.1);
}

.input-dock textarea {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: var(--text-main);
    font-family: 'Inter', sans-serif;
    font-size: 0.95rem;
    resize: none;
    line-height: 1.4;
    max-height: 200px;
}

.dock-actions {
    display: flex;
    align-items: center;
}

.btn-send {
    background: var(--primary-gradient);
    border: none;
    color: #0b0f19;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
    flex-shrink: 0;
}

.btn-send:hover {
    transform: scale(1.05);
    box-shadow: 0 0 12px rgba(56, 189, 248, 0.5);
}

.btn-send:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    transform: none;
}
'''
    with open(DEST_DIR / "static" / "style.css", "w", encoding="utf-8") as f:
        f.write(style_css)

    app_js = '''// AI Chatbot — Direct Streaming Controller (Zero Reasoning Overhead)
let activeSessionId = null;
let isStreaming = false;

// DOM references
const sessionsList = document.getElementById("sessionsList");
const newChatBtn = document.getElementById("newChatBtn");
const modelSelect = document.getElementById("modelSelect");
const sidebarModelName = document.getElementById("sidebarModelName");
const perfTag = document.getElementById("perfTag");
const messagesContainer = document.getElementById("messagesContainer");
const emptyState = document.getElementById("emptyState");
const chatForm = document.getElementById("chatForm");
const promptInput = document.getElementById("promptInput");
const sendBtn = document.getElementById("sendBtn");

// Markdown configuration
marked.setOptions({
    highlight: function(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            return hljs.highlight(code, { language: lang }).value;
        }
        return hljs.highlightAuto(code).value;
    },
    breaks: true
});

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
    loadModels();
    loadSessions();
    setupEventListeners();
});

function setupEventListeners() {
    newChatBtn.addEventListener("click", () => createNewChat());
    
    promptInput.addEventListener("input", () => {
        promptInput.style.height = "auto";
        promptInput.style.height = Math.min(promptInput.scrollHeight, 200) + "px";
    });

    promptInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event("submit"));
        }
    });

    window.addEventListener("keydown", (e) => {
        if (e.ctrlKey && e.key.toLowerCase() === "n") {
            e.preventDefault();
            createNewChat();
        }
    });

    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const prompt = promptInput.value.trim();
        if (!prompt || isStreaming) return;
        sendMessage(prompt);
    });
}

function usePrompt(text) {
    promptInput.value = text;
    promptInput.focus();
    chatForm.dispatchEvent(new Event("submit"));
}

async function loadModels() {
    try {
        const res = await fetch("/api/models");
        const data = await res.json();
        modelSelect.innerHTML = "";
        data.models.forEach(m => {
            const opt = document.createElement("option");
            opt.value = m;
            opt.textContent = m;
            if (m === data.default) opt.selected = true;
            modelSelect.appendChild(opt);
        });
        sidebarModelName.textContent = modelSelect.value;
        modelSelect.addEventListener("change", () => {
            sidebarModelName.textContent = modelSelect.value;
        });
    } catch (e) {
        console.error("Failed to load models:", e);
    }
}

async function loadSessions() {
    try {
        const res = await fetch("/api/sessions");
        const data = await res.json();
        activeSessionId = data.active_session_id;
        renderSessions(data.sessions);
        if (activeSessionId) {
            loadMessages(activeSessionId);
        }
    } catch (e) {
        console.error("Failed to load sessions:", e);
    }
}

function renderSessions(sessions) {
    sessionsList.innerHTML = "";
    sessions.forEach(sess => {
        const item = document.createElement("div");
        item.className = `session-item ${sess.id === activeSessionId ? "active" : ""}`;
        item.dataset.id = sess.id;

        const title = document.createElement("span");
        title.className = "session-title-text";
        title.textContent = sess.title || "New Chat";
        title.addEventListener("click", () => switchSession(sess.id));

        const delBtn = document.createElement("button");
        delBtn.className = "session-delete-btn";
        delBtn.innerHTML = "&#10005;";
        delBtn.title = "Delete conversation";
        delBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            deleteSession(sess.id);
        });

        item.appendChild(title);
        item.appendChild(delBtn);
        sessionsList.appendChild(item);
    });
}

async function switchSession(sessionId) {
    if (isStreaming || sessionId === activeSessionId) return;
    try {
        await fetch(`/api/sessions/${sessionId}/activate`, { method: "POST" });
        activeSessionId = sessionId;
        document.querySelectorAll(".session-item").forEach(el => {
            el.classList.toggle("active", el.dataset.id === sessionId);
        });
        loadMessages(sessionId);
    } catch (e) {
        console.error("Failed to activate session:", e);
    }
}

async function createNewChat() {
    if (isStreaming) return;
    try {
        const res = await fetch("/api/sessions", { method: "POST" });
        const newSess = await res.json();
        await loadSessions();
        await switchSession(newSess.id);
        promptInput.focus();
    } catch (e) {
        console.error("Failed to create session:", e);
    }
}

async function deleteSession(sessionId) {
    if (!confirm("Delete this conversation?")) return;
    try {
        await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
        await loadSessions();
    } catch (e) {
        console.error("Failed to delete session:", e);
    }
}

async function loadMessages(sessionId) {
    try {
        const res = await fetch(`/api/messages?session_id=${sessionId}`);
        const messages = await res.json();
        messagesContainer.innerHTML = "";

        if (messages.length === 0) {
            messagesContainer.appendChild(emptyState);
            emptyState.style.display = "flex";
            return;
        }

        emptyState.style.display = "none";
        messages.forEach(m => {
            if (m.role === "user") {
                appendUserMessage(m.content);
            } else if (m.role === "assistant") {
                appendAssistantMessage(m.content, m.tok_per_sec);
            }
        });
        scrollToBottom();
    } catch (e) {
        console.error("Failed to load messages:", e);
    }
}

function appendUserMessage(content) {
    emptyState.style.display = "none";
    const row = document.createElement("div");
    row.className = "message-row user";
    
    const bubble = document.createElement("div");
    bubble.className = "user-bubble";
    bubble.textContent = content;

    row.appendChild(bubble);
    messagesContainer.appendChild(row);
    scrollToBottom();
}

function appendAssistantMessage(content, tokPerSec = 0) {
    emptyState.style.display = "none";
    const row = document.createElement("div");
    row.className = "message-row assistant";

    const payload = document.createElement("div");
    payload.className = "assistant-payload";

    const avatar = document.createElement("div");
    avatar.className = "assistant-avatar";
    avatar.textContent = "💬";

    const body = document.createElement("div");
    body.className = "assistant-body";

    const prose = document.createElement("div");
    prose.className = "prose";
    prose.innerHTML = renderMarkdown(content);
    addCodeCopyButtons(prose);
    body.appendChild(prose);

    payload.appendChild(avatar);
    payload.appendChild(body);
    row.appendChild(payload);
    messagesContainer.appendChild(row);
    scrollToBottom();
}

function renderMarkdown(raw) {
    try {
        return marked.parse(raw);
    } catch (e) {
        return raw;
    }
}

function addCodeCopyButtons(container) {
    container.querySelectorAll("pre").forEach(pre => {
        if (pre.parentElement.classList.contains("code-block-wrapper")) return;
        
        const wrapper = document.createElement("div");
        wrapper.className = "code-block-wrapper";

        const header = document.createElement("div");
        header.className = "code-header";
        
        const codeEl = pre.querySelector("code");
        const langClass = codeEl ? Array.from(codeEl.classList).find(c => c.startsWith("language-")) : "";
        const langName = langClass ? langClass.replace("language-", "") : "code";
        header.innerHTML = `<span>${langName}</span>`;

        const copyBtn = document.createElement("button");
        copyBtn.className = "copy-btn";
        copyBtn.textContent = "Copy";
        copyBtn.addEventListener("click", () => {
            navigator.clipboard.writeText(pre.innerText).then(() => {
                copyBtn.textContent = "Copied!";
                setTimeout(() => copyBtn.textContent = "Copy", 1500);
            });
        });

        header.appendChild(copyBtn);
        pre.parentNode.insertBefore(wrapper, pre);
        wrapper.appendChild(header);
        wrapper.appendChild(pre);
    });
}

function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

async function sendMessage(prompt) {
    isStreaming = true;
    sendBtn.disabled = true;
    promptInput.value = "";
    promptInput.style.height = "auto";

    appendUserMessage(prompt);

    // Setup streaming Assistant UI
    const row = document.createElement("div");
    row.className = "message-row assistant";
    const payload = document.createElement("div");
    payload.className = "assistant-payload";
    const avatar = document.createElement("div");
    avatar.className = "assistant-avatar";
    avatar.textContent = "💬";
    const body = document.createElement("div");
    body.className = "assistant-body";

    const prose = document.createElement("div");
    prose.className = "prose";
    const cursor = document.createElement("span");
    cursor.className = "typing-cursor";

    body.appendChild(prose);
    body.appendChild(cursor);
    payload.appendChild(avatar);
    payload.appendChild(body);
    row.appendChild(payload);
    messagesContainer.appendChild(row);
    scrollToBottom();

    let rawAssistantContent = "";
    const model = modelSelect.value;

    const streamUrl = `/api/chat/stream?prompt=${encodeURIComponent(prompt)}&session_id=${encodeURIComponent(activeSessionId || "")}&model=${encodeURIComponent(model)}`;
    const eventSource = new EventSource(streamUrl);

    eventSource.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);

            if (data.type === "session_title") {
                loadSessions();
            } else if (data.type === "token") {
                rawAssistantContent += data.chunk;
                prose.innerHTML = renderMarkdown(rawAssistantContent);
                scrollToBottom();
            } else if (data.type === "done") {
                if (data.tok_per_sec) {
                    perfTag.textContent = `⚡ ${data.tok_per_sec} tok/s`;
                }
                if (cursor.parentNode) cursor.remove();
                addCodeCopyButtons(prose);
                eventSource.close();
                isStreaming = false;
                sendBtn.disabled = false;
                promptInput.focus();
            } else if (data.type === "error") {
                prose.innerHTML += `<p style="color:#f87171;">⚠️ ${data.message}</p>`;
                if (cursor.parentNode) cursor.remove();
                eventSource.close();
                isStreaming = false;
                sendBtn.disabled = false;
            }
        } catch (err) {
            console.error("SSE parse error:", err);
        }
    };

    eventSource.onerror = () => {
        if (cursor.parentNode) cursor.remove();
        eventSource.close();
        isStreaming = false;
        sendBtn.disabled = false;
    };
}
'''
    with open(DEST_DIR / "static" / "app.js", "w", encoding="utf-8") as f:
        f.write(app_js)
    print("[OK] static/ frontend files written (clean direct stream UI)")

def main():
    print(f"Scaffolding AI Chatbot (Zero Reasoning / Pure Stream) into: {DEST_DIR}...")
    setup_directories()
    copy_agents_roster()
    create_config_files()
    create_models_files()
    create_core_files()
    create_server_files()
    create_frontend_files()
    print("\\n[SUCCESS] AI Chatbot successfully updated for pure direct streaming!")

if __name__ == "__main__":
    main()
