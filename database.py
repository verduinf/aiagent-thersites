"""
SQLite Persistence Layer for AI Agent Thersites
Handles session management, user-facing episodic memory, pinned context, and transient scratch messages.
"""
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional
from config import DB_PATH, ROLLING_BUFFER_CHAR_LIMIT, PINNED_CONTEXT_CHAR_LIMIT

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                sequence_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_pinned INTEGER DEFAULT 0,
                token_estimate INTEGER DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scratch_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                action_name TEXT,
                raw_payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        """)
        # Intern DB Scratchpad Table (Full CRUD for Thersites)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS thersites_scratchpad (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()
        
    get_or_create_active_session()

def create_session(title: str = "New Session") -> Dict[str, Any]:
    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE sessions SET is_active = 0")
        cursor.execute("""
            INSERT INTO sessions (id, title, created_at, updated_at, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, (session_id, title, now, now))
        conn.commit()
    finally:
        conn.close()
    return {"id": session_id, "title": title, "created_at": now, "updated_at": now, "is_active": 1}

def get_recent_sessions(limit: int = 5) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.title, s.created_at, s.updated_at, s.is_active,
                   COUNT(m.id) as message_count
            FROM sessions s
            LEFT JOIN messages m ON s.id = m.session_id
            GROUP BY s.id
            ORDER BY s.updated_at DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_or_create_active_session() -> Dict[str, Any]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE is_active = 1 LIMIT 1")
        row = cursor.fetchone()
        if row:
            return dict(row)
    finally:
        conn.close()
        
    return create_session(title="Initial Intern Session")

def set_active_session(session_id: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE sessions SET is_active = 0")
        cursor.execute("UPDATE sessions SET is_active = 1 WHERE id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def add_message(session_id: str, role: str, content: str, is_pinned: int = 0) -> Dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,))
        count = cursor.fetchone()[0]
        sequence_id = count + 1
        token_estimate = len(content) // 4
        
        cursor.execute("""
            INSERT INTO messages (session_id, sequence_id, role, content, created_at, is_pinned, token_estimate)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (session_id, sequence_id, role, content, now, is_pinned, token_estimate))
        
        msg_id = cursor.lastrowid
        cursor.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        conn.commit()
        
        return {
            "id": msg_id,
            "session_id": session_id,
            "sequence_id": sequence_id,
            "role": role,
            "content": content,
            "created_at": now,
            "is_pinned": is_pinned,
            "token_estimate": token_estimate
        }
    finally:
        conn.close()

def toggle_message_pin(message_id: int) -> Dict[str, Any]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT is_pinned FROM messages WHERE id = ?", (message_id,))
        row = cursor.fetchone()
        if not row:
            return {"status": "error", "message": "Message not found"}
        
        new_state = 1 if row["is_pinned"] == 0 else 0
        cursor.execute("UPDATE messages SET is_pinned = ? WHERE id = ?", (new_state, message_id))
        conn.commit()
        return {"status": "success", "message_id": message_id, "is_pinned": new_state}
    finally:
        conn.close()

def get_pinned_messages(session_id: str, max_chars: int = PINNED_CONTEXT_CHAR_LIMIT) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM messages 
            WHERE session_id = ? AND is_pinned = 1
            ORDER BY sequence_id ASC
        """, (session_id,))
        rows = cursor.fetchall()
        
        results = []
        total_chars = 0
        for r in rows:
            d = dict(r)
            if total_chars + len(d["content"]) <= max_chars:
                results.append(d)
                total_chars += len(d["content"])
            else:
                break
        return results
    finally:
        conn.close()

def get_rolling_messages(session_id: str, max_chars: int = ROLLING_BUFFER_CHAR_LIMIT) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM messages 
            WHERE session_id = ? 
            ORDER BY sequence_id DESC
        """, (session_id,))
        rows = cursor.fetchall()
        
        selected = []
        total_chars = 0
        for r in rows:
            d = dict(r)
            if total_chars + len(d["content"]) <= max_chars:
                selected.append(d)
                total_chars += len(d["content"])
            else:
                break
                
        selected.reverse()
        return selected
    finally:
        conn.close()

def get_all_messages(session_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM messages 
            WHERE session_id = ? 
            ORDER BY sequence_id ASC
        """, (session_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def add_scratch_message(session_id: str, turn_index: int, action_name: str, raw_payload: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO scratch_messages (session_id, turn_index, action_name, raw_payload, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, turn_index, action_name, raw_payload, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    finally:
        conn.close()

def execute_user_sql_query(query: str) -> List[Dict[str, Any]]:
    """Executes validated SQL query against SQLite database."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        if query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        else:
            conn.commit()
            return [{"status": "success", "rows_affected": cursor.rowcount}]
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully with thersites_scratchpad table!")
