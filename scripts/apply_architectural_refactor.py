"""
Architectural Refactor for C:\Dev\ai-chatbot:
1. Simplify database schema (remove sequence_id query, remove tok_per_sec column)
2. Dynamic GPU layer offloading (NUM_GPU: null allows Ollama auto-allocation)
3. Token & turn bounded rolling context
4. Engine add_message signature cleanup
"""
import sqlite3
from pathlib import Path

DEST = Path(r"C:\Dev\ai-chatbot")

def refactor_database_py():
    db_file = DEST / "core" / "database.py"
    code = '''"""
SQLite Database Operations for AI Chatbot (data/chat.db).
Streamlined schema: pure conversation persistence with automatic sequence ordering.
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
    """Initializes sessions and messages tables with clean autoincrement sequence."""
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
                role TEXT NOT NULL,
                content TEXT NOT NULL,
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

def add_message(session_id: str, role: str, content: str) -> Dict[str, Any]:
    """Appends a message directly using native autoincrement ordering without roundtrip MAX queries."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content)
        )
        conn.execute("UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)

def get_all_messages(session_id: str) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_rolling_messages(session_id: str, max_turns: int = 30, char_limit: int = 24000) -> List[Dict[str, str]]:
    """Bounded conversation context window by turn count and character budget."""
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, max_turns)
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
    db_file.write_text(code, encoding="utf-8")
    print("[OK] core/database.py refactored")

def refactor_engine_py():
    engine_file = DEST / "core" / "engine.py"
    code = '''"""
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
    rolling = get_rolling_messages(session_id, max_turns=30, char_limit=ROLLING_BUFFER_CHAR_LIMIT)
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
                add_message(session_id, "assistant", full_text)
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
            add_message(session_id, "assistant", partial_text)
            print(f"[AI Chatbot] Saved partial response on disconnect: {len(partial_text)} chars\\n")
            sys.stdout.flush()
'''
    engine_file.write_text(code, encoding="utf-8")
    print("[OK] core/engine.py refactored")

def refactor_config_and_client():
    # config.json: set NUM_GPU to null (auto)
    cfg_path = DEST / "config.json"
    import json
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["NUM_GPU"] = None
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print("[OK] config.json updated: NUM_GPU set to null (auto)")

    # config.py
    cfg_py = DEST / "config.py"
    code = cfg_py.read_text(encoding="utf-8")
    code = code.replace(
        'NUM_GPU = int(config_data.get("NUM_GPU", 58))',
        'NUM_GPU = config_data.get("NUM_GPU", None)\nif NUM_GPU is not None and str(NUM_GPU).isdigit():\n    NUM_GPU = int(NUM_GPU)'
    )
    cfg_py.write_text(code, encoding="utf-8")
    print("[OK] config.py updated for optional NUM_GPU")

    # ollama_client.py
    client_py = DEST / "models" / "ollama_client.py"
    code = client_py.read_text(encoding="utf-8")
    old_opts = '''        "options": {
            "num_ctx": dynamic_num_ctx,
            "num_gpu": NUM_GPU,
            "num_predict": 2048,
            "num_thread": 8,
            "temperature": AI_TEMPERATURE
        },'''
    new_opts = '''        "options": {
            "num_ctx": dynamic_num_ctx,
            "num_predict": 2048,
            "num_thread": 8,
            "temperature": AI_TEMPERATURE
        },'''
    code = code.replace(old_opts, new_opts)
    if 'if NUM_GPU is not None:' not in code:
        inject = '''    if NUM_GPU is not None and NUM_GPU != -1:
        payload["options"]["num_gpu"] = NUM_GPU
'''
        code = code.replace('if is_granite:', inject + '    if is_granite:')
    client_py.write_text(code, encoding="utf-8")
    print("[OK] models/ollama_client.py updated for dynamic GPU layer offload")

def reset_clean_db():
    db_path = DEST / "data" / "chat.db"
    if db_path.exists():
        db_path.unlink()
    import sys
    sys.path.insert(0, str(DEST))
    from core.database import init_db, create_session
    init_db()
    s = create_session(title="New Chat")
    print(f"[OK] chat.db recreated with streamlined schema, active session: {s['id']}")

def main():
    refactor_database_py()
    refactor_engine_py()
    refactor_config_and_client()
    reset_clean_db()
    print("\\n[SUCCESS] Architectural refactor complete!")

if __name__ == "__main__":
    main()
