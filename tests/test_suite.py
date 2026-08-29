"""
Argus Test Suite Guardian — AI Agent Thersites Test Suite
Verifies SQLite storage, multi-session management, The Warden guardrail rules,
JSON fuzzy extraction, SQL query safety, and Turn-1 telemetry.

Uses persistent thersites.db with test roles (test_user, test_assistant),
and automatically cleans up test data upon completion via database.cleanup_test_data().
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path("C:/Dev/aiagent-thersites").resolve()))

from database import (
    init_db, create_session, get_recent_sessions, add_message,
    toggle_message_pin, get_pinned_messages, get_rolling_messages,
    get_all_messages, add_scratch_message, cleanup_test_data
)
from warden import inspect_and_authorize, WardenViolation, validate_url, validate_write_path, validate_sql_query
from engine import extract_fuzzy_json, run_subagent_summarizer
from config import SANDBOX_DIR

class TestThersitesSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        cleanup_test_data()
        cls.test_session = create_session("Argus Unit Test Session")

    @classmethod
    def tearDownClass(cls):
        cleanup_test_data()

    def test_01_database_session_and_messages(self):
        session_id = self.test_session["id"]
        msg1 = add_message(session_id, "test_user", "Hello Thersites, what is 2+2?")
        self.assertEqual(msg1["sequence_id"], 1)
        self.assertIn("created_at", msg1)
        
        msg2 = add_message(session_id, "test_assistant", "Boss, 2+2 is 4!")
        self.assertEqual(msg2["sequence_id"], 2)

    def test_02_message_pinning(self):
        session_id = self.test_session["id"]
        msg = add_message(session_id, "test_user", "Crucial requirement: Always output JSON.")
        msg_id = msg["id"]
        
        res = toggle_message_pin(msg_id)
        self.assertEqual(res["is_pinned"], 1)
        
        res2 = toggle_message_pin(msg_id)
        self.assertEqual(res2["is_pinned"], 0)

    def test_03_warden_nu_nl_whitelist(self):
        ok, msg, params = inspect_and_authorize("web_fetch", {"url": "https://nu.nl/tech"})
        self.assertTrue(ok)
        
        ok, msg, params = inspect_and_authorize("web_fetch", {"url": "https://python.org"})
        self.assertFalse(ok)
        self.assertIn("Unauthorized domain", msg)

    def test_04_warden_sandbox_crud(self):
        sandbox_file = str(SANDBOX_DIR / "intern_test.txt")
        
        ok, msg, params = inspect_and_authorize("write_to_file", {"filepath": sandbox_file})
        self.assertTrue(ok)
        
        ok, msg, params = inspect_and_authorize("read_file", {"filepath": sandbox_file})
        self.assertTrue(ok)
        
        ok, msg, params = inspect_and_authorize("delete_file", {"filepath": sandbox_file})
        self.assertTrue(ok)
        
        system_path = "C:/Windows/System32/hacked.dll"
        ok, msg, params = inspect_and_authorize("write_to_file", {"filepath": system_path})
        self.assertFalse(ok)
        self.assertIn("Path sandbox violation", msg)

    def test_05_warden_sql_query_safety(self):
        ok, msg, params = inspect_and_authorize("sqlite_query_executor", {"query": "SELECT * FROM messages LIMIT 5;"})
        self.assertTrue(ok)
        
        ok, msg, params = inspect_and_authorize("sqlite_query_executor", {
            "query": "INSERT INTO thersites_scratchpad (key, value, updated_at) VALUES ('task_1', 'done', '2026-08-29');"
        })
        self.assertTrue(ok)
        
        ok, msg, params = inspect_and_authorize("sqlite_query_executor", {"query": "DELETE FROM messages WHERE id = 1;"})
        self.assertFalse(ok)
        self.assertIn("restricted strictly to table 'thersites_scratchpad'", msg)

    def test_06_fuzzy_json_parser(self):
        raw_llm_output = """
        Sure Boss! Here is my response:
        ```json
        {
            "thought": "I should answer politely.",
            "content": "Here is the summary!",
            "actions": [
                {"id": "act_1", "tool": "none", "params": {}}
            ]
        }
        ```
        Hope that helps!
        """
        parsed = extract_fuzzy_json(raw_llm_output)
        self.assertEqual(parsed["thought"], "I should answer politely.")
        self.assertEqual(parsed["content"], "Here is the summary!")
        self.assertEqual(len(parsed["actions"]), 1)

if __name__ == "__main__":
    unittest.main()
