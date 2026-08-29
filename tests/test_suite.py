"""
Argus Test Suite Guardian — AI Agent Thersites Test Suite
Verifies SQLite storage, multi-session management, Bouncer guardrail rules,
JSON fuzzy extraction, and Turn-1 telemetry.
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path("C:/Dev/aiagent-thersites").resolve()))

from database import (
    init_db, create_session, get_recent_sessions, add_message,
    toggle_message_pin, get_pinned_messages, get_rolling_messages,
    get_all_messages, add_scratch_message
)
from bouncer import inspect_and_authorize, BouncerViolation, validate_url, validate_write_path
from engine import extract_fuzzy_json, run_subagent_summarizer
from config import SANDBOX_DIR

class TestThersitesSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.test_session = create_session("Argus Unit Test Session")

    def test_01_database_session_and_messages(self):
        session_id = self.test_session["id"]
        msg1 = add_message(session_id, "user", "Hello Thersites, what is 2+2?")
        self.assertEqual(msg1["sequence_id"], 1)
        self.assertIn("created_at", msg1)
        
        msg2 = add_message(session_id, "assistant", "Boss, 2+2 is 4!")
        self.assertEqual(msg2["sequence_id"], 2)
        
        all_msgs = get_all_messages(session_id)
        self.assertGreaterEqual(len(all_msgs), 2)
        self.assertEqual(all_msgs[0]["role"], "user")

    def test_02_message_pinning(self):
        session_id = self.test_session["id"]
        msg = add_message(session_id, "user", "Crucial requirement: Always output JSON.")
        msg_id = msg["id"]
        
        res = toggle_message_pin(msg_id)
        self.assertEqual(res["is_pinned"], 1)
        
        pinned = get_pinned_messages(session_id)
        self.assertTrue(any(p["id"] == msg_id for p in pinned))
        
        res2 = toggle_message_pin(msg_id)
        self.assertEqual(res2["is_pinned"], 0)

    def test_03_bouncer_nu_nl_whitelist(self):
        # Whitelisted URL nu.nl
        ok, msg, params = inspect_and_authorize("web_fetch", {"url": "https://nu.nl/tech"})
        self.assertTrue(ok)
        
        # Unauthorized URL python.org (under new single-domain policy)
        ok, msg, params = inspect_and_authorize("web_fetch", {"url": "https://python.org"})
        self.assertFalse(ok)
        self.assertIn("Unauthorized domain", msg)

    def test_04_bouncer_sandbox_crud(self):
        sandbox_file = str(SANDBOX_DIR / "intern_test.txt")
        
        # Write
        ok, msg, params = inspect_and_authorize("write_to_file", {"filepath": sandbox_file})
        self.assertTrue(ok)
        
        # Read
        ok, msg, params = inspect_and_authorize("read_file", {"filepath": sandbox_file})
        self.assertTrue(ok)
        
        # Delete
        ok, msg, params = inspect_and_authorize("delete_file", {"filepath": sandbox_file})
        self.assertTrue(ok)
        
        # Sandbox Violation
        system_path = "C:/Windows/System32/hacked.dll"
        ok, msg, params = inspect_and_authorize("write_to_file", {"filepath": system_path})
        self.assertFalse(ok)
        self.assertIn("Path sandbox violation", msg)

    def test_05_fuzzy_json_parser(self):
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
