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
from fastapi import FastAPI, HTTPException, Query, Request, Response, File, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import STATIC_DIR, SANDBOX_DIR, UPLOADS_DIR, MODEL_NAME, AVAILABLE_MODELS
from database import (
    init_db, create_session, set_active_session, get_recent_sessions,
    get_or_create_active_session, add_message, toggle_message_pin,
    get_all_messages, cleanup_test_data, delete_message
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

app = FastAPI(title="Local Intern Thersites", version="1.0.0", lifespan=lifespan)

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
app.mount("/images", StaticFiles(directory="Images"), name="images")
app.mount("/sandbox", StaticFiles(directory=SANDBOX_DIR), name="sandbox")

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

@app.get("/api/models")
async def get_models():
    # Reload dynamically in case config.json was edited live
    import json
    from config import CONFIG_JSON_PATH
    models = list(AVAILABLE_MODELS)
    default_m = MODEL_NAME
    if CONFIG_JSON_PATH.exists():
        try:
            with open(CONFIG_JSON_PATH, "r", encoding="utf-8-sig") as f:
                cdata = json.load(f)
                if "AVAILABLE_MODELS" in cdata:
                    models = cdata["AVAILABLE_MODELS"]
                if "MODEL_NAME" in cdata:
                    default_m = cdata["MODEL_NAME"]
        except Exception:
            pass
    return {"models": models, "default": default_m}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        clean_name = os.path.basename(file.filename).replace(" ", "_")
        target_path = UPLOADS_DIR / clean_name
        
        content = await file.read()
        with open(target_path, "wb") as f:
            f.write(content)
            
        return {
            "status": "success",
            "filepath": str(target_path).replace("\\", "/"),
            "filename": clean_name,
            "url": f"/sandbox/uploads/{clean_name}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

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

@app.delete("/api/messages/{message_id}")
async def delete_message_endpoint(message_id: int):
    deleted = delete_message(message_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "success", "message_id": message_id}

@app.get("/api/chat/stream")
async def stream_chat(prompt: str, session_id: Optional[str] = None, image_path: Optional[str] = None, think: Optional[str] = "off", model: Optional[str] = None):
    if not session_id:
        active_sess = get_or_create_active_session()
        session_id = active_sess["id"]
        
    set_active_session(session_id)

    async def event_generator():
        generator = run_agent_inner_loop(session_id, prompt, image_path=image_path, think_mode=think, model_name=model)
        for chunk in generator:
            yield f"data: {json.dumps(chunk)}\n\n"
            await asyncio.sleep(0.01)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    kill_existing_port_process(port=8000)
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
