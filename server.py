"""
FastAPI Server & SSE API Endpoints for AI Agent Thersites
Provides session routing, timeline queries, pin management, and streaming inner-loop responses.
"""
import os
import json
import asyncio
import subprocess
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import STATIC_DIR, MODEL_NAME
from database import (
    init_db, create_session, set_active_session, get_recent_sessions,
    get_or_create_active_session, add_message, toggle_message_pin,
    get_all_messages, cleanup_test_data
)
from engine import run_agent_inner_loop, prewarm_ollama_model

def kill_existing_port_process(port: int = 8000):
    """Terminates any old orphaned process listening on the target port before starting a new server instance."""
    try:
        cmd = f'netstat -ano | findstr LISTENING | findstr :{port}'
        output = subprocess.check_output(cmd, shell=True, text=True, errors='ignore')
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
    cleanup_test_data()
    asyncio.create_task(asyncio.to_thread(prewarm_ollama_model))
    yield

app = FastAPI(title="AI Agent Thersites", version="1.0.0", lifespan=lifespan)

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

class ChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None

@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/favicon.ico")
async def favicon_endpoint():
    return Response(status_code=204)

@app.get("/api/sessions")
async def list_sessions():
    active_session = get_or_create_active_session()
    sessions = get_recent_sessions()
    return {"sessions": sessions, "active_session_id": active_session["id"]}

@app.post("/api/sessions")
async def create_new_session(session_id: Optional[str] = None, title: Optional[str] = None):
    sess = create_session(session_id, title)
    return sess

@app.post("/api/sessions/{session_id}/activate")
async def activate_session_endpoint(session_id: str):
    sess = set_active_session(session_id)
    return sess

@app.get("/api/messages")
async def list_messages(session_id: Optional[str] = None):
    if not session_id:
        active_sess = get_or_create_active_session()
        session_id = active_sess["id"]
    messages = get_all_messages(session_id)
    return messages

@app.post("/api/messages/{message_id}/pin")
async def toggle_pin_endpoint(message_id: int):
    try:
        updated = toggle_message_pin(message_id)
        return updated
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/chat/stream")
async def stream_chat(prompt: str, session_id: Optional[str] = None):
    if not session_id:
        active_sess = get_or_create_active_session()
        session_id = active_sess["id"]
        
    set_active_session(session_id)

    async def event_generator():
        generator = run_agent_inner_loop(session_id, prompt)
        for chunk in generator:
            yield f"data: {json.dumps(chunk)}

"
            await asyncio.sleep(0.01)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    kill_existing_port_process(port=8000)
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
