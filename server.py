"""
FastAPI Server for AI Agent Thersites
Provides REST & SSE Streaming API endpoints and serves the clean dark-mode Web UI.
"""
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel

from config import STATIC_DIR, ROLLING_BUFFER_CHAR_LIMIT, PINNED_CONTEXT_CHAR_LIMIT, MODEL_NAME
from database import (
    init_db, get_or_create_active_session, get_recent_sessions,
    create_session, set_active_session, get_all_messages,
    get_pinned_messages, toggle_message_pin
)
from engine import run_agent_inner_loop

app = FastAPI(title="AI Agent Thersites API", version="1.0.0")

# Mount Static Files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/", response_class=HTMLResponse)
def read_root():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>AI Agent Thersites Server Running</h1><p>Index UI initializing...</p>"

@app.get("/api/sessions")
def list_sessions():
    sessions = get_recent_sessions(limit=5)
    active = get_or_create_active_session()
    return {"sessions": sessions, "active_session_id": active["id"]}

@app.post("/api/sessions")
def new_session(payload: dict = Body(default={})):
    title = payload.get("title", "New Session")
    sess = create_session(title)
    return {"status": "success", "session": sess}

@app.post("/api/sessions/active")
def switch_active_session(payload: dict = Body(...)):
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    success = set_active_session(session_id)
    return {"status": "success" if success else "error"}

@app.get("/api/messages")
def get_messages():
    active = get_or_create_active_session()
    session_id = active["id"]
    all_msgs = get_all_messages(session_id)
    pinned_msgs = get_pinned_messages(session_id, PINNED_CONTEXT_CHAR_LIMIT)
    
    # Calculate telemetry metrics
    total_chars = sum(len(m["content"]) for m in all_msgs)
    pinned_chars = sum(len(m["content"]) for m in pinned_msgs)
    
    return {
        "active_session": active,
        "model_name": MODEL_NAME,
        "messages": all_msgs,
        "pinned_messages": pinned_msgs,
        "telemetry": {
            "total_messages": len(all_msgs),
            "total_chars": total_chars,
            "pinned_chars": pinned_chars,
            "pinned_limit": PINNED_CONTEXT_CHAR_LIMIT,
            "rolling_limit": ROLLING_BUFFER_CHAR_LIMIT
        }
    }

@app.post("/api/pin/{message_id}")
def pin_message(message_id: int):
    result = toggle_message_pin(message_id)
    return result

class ChatRequest(BaseModel):
    prompt: str

@app.post("/api/chat")
def chat_stream(request: ChatRequest):
    active = get_or_create_active_session()
    session_id = active["id"]
    
    def event_generator():
        for event in run_agent_inner_loop(session_id, request.prompt):
            event_data = f"data: {json.dumps(event)}\n\n"
            yield event_data
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
