"""
Fix Windows console encoding (cp1252 -> utf-8) and safe telemetry printing.
"""
from pathlib import Path

DEST_DIR = Path(r"C:\Dev\ai-chatbot")

def fix_all():
    # 1. Update run_server.cmd and run_server verbose.cmd with chcp 65001
    for name in ["run_server.cmd", "run_server verbose.cmd"]:
        cmd_path = DEST_DIR / name
        content = cmd_path.read_text(encoding="utf-8")
        if "chcp 65001" not in content:
            content = "@echo off\nchcp 65001 > nul\n" + content.replace("@echo off\n", "")
            cmd_path.write_text(content, encoding="utf-8")
            print(f"[OK] Added chcp 65001 to {name}")

    # 2. Update server.py with sys.stdout reconfigure
    server_path = DEST_DIR / "server.py"
    server_code = server_path.read_text(encoding="utf-8")
    reconfig_code = """import sys
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
"""
    if "reconfigure" not in server_code:
        server_code = reconfig_code + server_code
        server_path.write_text(server_code, encoding="utf-8")
        print("[OK] Added stdout UTF-8 reconfigure to server.py")

    # 3. Update engine.py with sys.stdout reconfigure and clean safe prints
    engine_path = DEST_DIR / "core" / "engine.py"
    engine_code = '''"""
Streaming Conversation Engine for AI Chatbot (Direct response, zero reasoning).
"""
import sys
import time
from typing import Generator, Dict, Any, Optional

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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
    Guarantees database persistence before yielding 'done'.
    """
    effective_model = model_name or MODEL_NAME
    
    print("\\n" + "=" * 60)
    print(f"[AI Chatbot] Session: {session_id} | Model: {effective_model}")
    print(f"[User Prompt]: {user_prompt.strip()}")
    print("=" * 60)
    sys.stdout.flush()
    
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
    saved = False

    try:
        # 3. Stream direct tokens from Ollama
        for chunk in stream_ollama_chat(messages, model=effective_model):
            c_type = chunk.get("type")
            if c_type == "token":
                t = chunk.get("chunk", "")
                assistant_content.append(t)
                yield chunk
            elif c_type == "done":
                tok_per_sec = chunk.get("tok_per_sec", 0.0)
                # PERSIST BEFORE YIELDING DONE
                full_text = "".join(assistant_content)
                add_message(session_id, "assistant", full_text, tok_per_sec=tok_per_sec)
                saved = True
                print(f"[AI Chatbot] Response complete: {len(full_text)} chars | {tok_per_sec} tok/s\\n")
                sys.stdout.flush()
                yield chunk
                return
            elif c_type == "error":
                print(f"[AI Chatbot Error]: {chunk.get('message')}")
                sys.stdout.flush()
                yield chunk
                return
    finally:
        # Guarantees message persistence even if client disconnects early
        if not saved and assistant_content:
            partial_text = "".join(assistant_content)
            add_message(session_id, "assistant", partial_text, tok_per_sec=tok_per_sec)
            print(f"[AI Chatbot] Saved partial response on disconnect: {len(partial_text)} chars\\n")
            sys.stdout.flush()
'''
    engine_path.write_text(engine_code, encoding="utf-8")
    print("[OK] engine.py updated with robust encoding & flushing")

if __name__ == "__main__":
    fix_all()
