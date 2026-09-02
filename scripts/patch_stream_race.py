"""
Patch race conditions:
1. Prevent loadSessions() from blowing away messagesContainer mid-stream
2. Persist assistant message in engine.py BEFORE yielding 'done' and in 'finally' block
"""
from pathlib import Path

DEST_DIR = Path(r"C:\Dev\ai-chatbot")

def patch_engine():
    engine_path = DEST_DIR / "core" / "engine.py"
    code = '''"""
Streaming Conversation Engine for AI Chatbot (Direct response, zero reasoning).
"""
import time
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
    Guarantees database persistence before yielding 'done'.
    """
    effective_model = model_name or MODEL_NAME
    
    print("\\n" + "=" * 60)
    print(f"⚡ [AI Chatbot] Session: {session_id} | Model: {effective_model}")
    print(f"💬 Prompt: {user_prompt.strip()}")
    print("=" * 60)
    
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
                print(f"✅ [AI Chatbot] Response complete: {len(full_text)} chars | {tok_per_sec} tok/s\\n")
                yield chunk
                return
            elif c_type == "error":
                print(f"❌ [AI Chatbot] Error: {chunk.get('message')}")
                yield chunk
                return
    finally:
        # Guarantees message persistence even if client disconnects early
        if not saved and assistant_content:
            partial_text = "".join(assistant_content)
            add_message(session_id, "assistant", partial_text, tok_per_sec=tok_per_sec)
            print(f"💾 [AI Chatbot] Saved partial response on disconnect: {len(partial_text)} chars\\n")
'''
    engine_path.write_text(code, encoding="utf-8")
    print("[OK] engine.py patched with pre-done persistence and finally guard")

def patch_frontend():
    app_js_path = DEST_DIR / "static" / "app.js"
    code = app_js_path.read_text(encoding="utf-8")
    
    # 1. Update loadSessions signature to allow loadSessions(reloadMessages = false)
    old_load_sessions = '''async function loadSessions() {
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
}'''

    new_load_sessions = '''async function loadSessions(reloadMessages = false) {
    try {
        const res = await fetch("/api/sessions");
        const data = await res.json();
        activeSessionId = data.active_session_id;
        renderSessions(data.sessions);
        if (reloadMessages && activeSessionId) {
            loadMessages(activeSessionId);
        }
    } catch (e) {
        console.error("Failed to load sessions:", e);
    }
}'''

    code = code.replace(old_load_sessions, new_load_sessions)

    # 2. Fix session_title handler in eventSource so it doesn't reload messages
    code = code.replace(
        'if (data.type === "session_title") {\n                loadSessions();',
        'if (data.type === "session_title") {\n                loadSessions(false);'
    )

    # 3. Fix initial load
    code = code.replace(
        'loadSessions();\n    setupEventListeners();',
        'loadSessions(true);\n    setupEventListeners();'
    )

    # 4. Fix deleteSession
    code = code.replace(
        'await loadSessions();\n    }',
        'await loadSessions(true);\n    }'
    )

    app_js_path.write_text(code, encoding="utf-8")
    print("[OK] app.js patched so loadSessions(false) never wipes active stream")

    # Update index.html version to v=4 for cache bust
    index_path = DEST_DIR / "static" / "index.html"
    index_content = index_path.read_text(encoding="utf-8")
    index_content = index_content.replace("app.js?v=3", "app.js?v=4").replace("style.css?v=3", "style.css?v=4")
    index_path.write_text(index_content, encoding="utf-8")
    print("[OK] index.html version bumped to v=4")

def main():
    patch_engine()
    patch_frontend()
    print("[SUCCESS] All race conditions resolved!")

if __name__ == "__main__":
    main()
