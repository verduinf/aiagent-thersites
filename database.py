"""
SQLite Database Operations for AI Agent Thersites
Handles session persistence, episodic message storage, sequence ordering, and rolling/pinned context queries.
Excludes test_% roles from user-facing context and provides test cleanup utilities.
"""
import sqlite3
import os
import time
from typing import List, Dict, Any, Optional
from pathlib import Path
from config import DB_PATH

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT DEFAULT 'New Session',
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
                is_pinned INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS thersites_scratchpad (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scratch_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                action_name TEXT,
                raw_payload TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        
        conn.commit()

def create_session(session_id: Optional[str] = None, title: Optional[str] = None) -> Dict[str, Any]:
    with get_db_connection() as conn:
        conn.execute("UPDATE sessions SET is_active = 0")
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        if not session_id:
            session_id = f"session_{time.strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"
        if not title:
            title = session_id
            
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at, is_active) VALUES (?, ?, ?, ?, 1)",
            (session_id, title, now, now)
        )
        conn.commit()
        return {"id": session_id, "title": title, "created_at": now, "is_active": 1}

def set_active_session(session_id: str) -> Dict[str, Any]:
    with get_db_connection() as conn:
        conn.execute("UPDATE sessions SET is_active = 0")
        conn.execute("UPDATE sessions SET is_active = 1 WHERE id = ?", (session_id,))
        conn.commit()
        return {"id": session_id, "is_active": 1}

def get_recent_sessions(limit: int = 20) -> List[Dict[str, Any]]:
    """Returns sessions ordered by the timestamp of their most recent message."""
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT s.id, s.title, s.created_at, s.is_active, 
                   COALESCE(MAX(m.created_at), s.created_at) as last_activity
            FROM sessions s
            LEFT JOIN messages m ON s.id = m.session_id AND m.role NOT LIKE 'test_%'
            GROUP BY s.id
            ORDER BY last_activity DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

def get_or_create_active_session() -> Dict[str, Any]:
    """Returns the session with the most recent message, ensuring it is set active."""
    with get_db_connection() as conn:
        active = conn.execute("""
            SELECT s.id, s.title, s.created_at, s.is_active,
                   COALESCE(MAX(m.created_at), s.created_at) as last_activity
            FROM sessions s
            LEFT JOIN messages m ON s.id = m.session_id AND m.role NOT LIKE 'test_%'
            GROUP BY s.id
            ORDER BY last_activity DESC
            LIMIT 1
        """).fetchone()
        
        if active:
            active_dict = dict(active)
            conn.execute("UPDATE sessions SET is_active = 0")
            conn.execute("UPDATE sessions SET is_active = 1 WHERE id = ?", (active_dict["id"],))
            conn.commit()
            active_dict["is_active"] = 1
            return active_dict
            
        return create_session()

def add_message(session_id: str, role: str, content: str) -> Dict[str, Any]:
    with get_db_connection() as conn:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        seq_row = conn.execute(
            "SELECT COALESCE(MAX(sequence_id), 0) + 1 as next_seq FROM messages WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        next_seq = seq_row["next_seq"]
        
        cursor = conn.execute(
            """INSERT INTO messages (session_id, sequence_id, role, content, is_pinned, created_at)
               VALUES (?, ?, ?, ?, 0, ?)""",
            (session_id, next_seq, role, content, now)
        )
        msg_id = cursor.lastrowid
        conn.commit()
        
        msg = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
        return dict(msg)

def toggle_message_pin(message_id: int) -> Dict[str, Any]:
    with get_db_connection() as conn:
        current = conn.execute("SELECT is_pinned FROM messages WHERE id = ?", (message_id,)).fetchone()
        if not current:
            raise ValueError(f"Message ID {message_id} not found.")
            
        new_pinned = 0 if current["is_pinned"] == 1 else 1
        conn.execute("UPDATE messages SET is_pinned = ? WHERE id = ?", (new_pinned, message_id))
        conn.commit()
        
        updated = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        return dict(updated)

def get_pinned_messages(session_id: str, char_limit: int = 5000) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM messages 
            WHERE session_id = ? AND is_pinned = 1 AND role NOT LIKE 'test_%'
            ORDER BY sequence_id ASC
        """, (session_id,)).fetchall()
        
        pinned = []
        acc_chars = 0
        for r in rows:
            content_len = len(r["content"])
            if acc_chars + content_len <= char_limit:
                pinned.append(dict(r))
                acc_chars += content_len
            else:
                break
        return pinned

def get_rolling_messages(session_id: str, char_limit: int = 20000) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM messages 
            WHERE session_id = ? AND is_pinned = 0 AND role NOT LIKE 'test_%'
            ORDER BY sequence_id DESC
        """, (session_id,)).fetchall()
        
        rolling_rev = []
        acc_chars = 0
        for r in rows:
            content_len = len(r["content"])
            if acc_chars + content_len <= char_limit:
                rolling_rev.append(dict(r))
                acc_chars += content_len
            else:
                break
                
        rolling_rev.reverse()
        return rolling_rev

def get_all_messages(session_id: str) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM messages 
            WHERE session_id = ? AND role NOT LIKE 'test_%'
            ORDER BY sequence_id ASC
        """, (session_id,)).fetchall()
        return [dict(r) for r in rows]

def add_scratch_message(session_id: str, turn_index: int, action_name: str, raw_payload: str) -> Dict[str, Any]:
    with get_db_connection() as conn:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        cursor = conn.execute("""
            INSERT INTO scratch_messages (session_id, turn_index, action_name, raw_payload, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, turn_index, action_name, raw_payload, now))
        row_id = cursor.lastrowid
        conn.commit()
        return {"id": row_id, "session_id": session_id, "turn_index": turn_index, "action_name": action_name}

def execute_user_sql_query(query: str) -> str:
    with get_db_connection() as conn:
        cursor = conn.execute(query)
        if query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            return f"QueryResult: {[dict(r) for r in rows]}"
        else:
            conn.commit()
            return f"Query executed successfully. Rows affected: {cursor.rowcount}"

def cleanup_test_data():
    """Purges test_ messages and test sessions created during unit testing."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM messages WHERE role LIKE 'test_%' OR session_id LIKE 'Argus%' OR session_id LIKE 'test_%'")
        conn.execute("DELETE FROM sessions WHERE id LIKE 'test_%' OR id LIKE 'Argus%'")
        conn.commit()
