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
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, str(Path("C:/Dev/aiagent-thersites").resolve()))

from database import (
    init_db, create_session, get_recent_sessions, add_message,
    toggle_message_pin, get_pinned_messages, get_rolling_messages,
    get_all_messages, add_scratch_message, cleanup_test_data, delete_message
)
from warden import inspect_and_authorize, WardenViolation, validate_url, validate_write_path, validate_sql_query
from engine import extract_fuzzy_json, clean_html_to_text
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

    def test_07_delete_message(self):

        session_id = self.test_session["id"]
        msg = add_message(session_id, "test_user", "Temporary typo message to delete")
        msg_id = msg["id"]
        
        self.assertTrue(delete_message(msg_id))
        all_msgs = get_all_messages(session_id)
        msg_ids = [m["id"] for m in all_msgs]
        self.assertNotIn(msg_id, msg_ids)


    @patch("requests.post")
    def test_08_pushover_notification(self, mock_post):
        # Ensure mock HTTP response so NO live network requests or phone buzzes occur
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status": 1}'
        mock_post.return_value = mock_resp

        # 1. Test Warden authorization for send_message and aliases
        ok, msg, params = inspect_and_authorize("send_message", {"message": "Test Alert", "title": "Unit Test"})
        self.assertTrue(ok)
        self.assertIn("authorized", msg.lower())
        
        ok, msg, params = inspect_and_authorize("send_message", {})
        self.assertFalse(ok)
        self.assertIn("missing", msg.lower())
        
        # 2. Test Engine execution with mocked network request
        from engine import execute_tool_call
        res = execute_tool_call({
            "id": "act_1",
            "tool": "send_message",
            "params": {"message": "Task complete!", "title": "Thersites Alert"}
        })
        self.assertEqual(res["status"], "success")
        self.assertTrue("Successfully dispatched" in res["result"] or "[SIMULATION]" in res["result"])


    @patch("requests.get")
    def test_09_download_image_tool(self, mock_get):
        # Mock HTTP GET response for image download
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR..."
        mock_get.return_value = mock_resp

        # 1. Test Warden authorization for download_image
        target_img = str(SANDBOX_DIR / "test_download.png")
        ok, msg, params = inspect_and_authorize("download_image", {
            "url": "https://media.nu.nl/m/test.jpg",
            "filepath": target_img
        })
        self.assertTrue(ok)
        self.assertIn("authorized", msg.lower())

        # Test unauthorized domain blocked
        ok, msg, params = inspect_and_authorize("download_image", {
            "url": "https://malicious.com/virus.exe",
            "filepath": target_img
        })
        self.assertFalse(ok)
        self.assertIn("unauthorized domain", msg.lower())

        # 2. Test Engine execution with mocked download
        from engine import execute_tool_call
        res = execute_tool_call({
            "id": "act_1",
            "tool": "download_image",
            "params": {
                "url": "https://media.nu.nl/m/test.jpg",
                "filepath": target_img
            }
        })
        self.assertEqual(res["status"], "success")
        self.assertIn("Successfully downloaded image", res["result"])
        if os.path.exists(target_img):
            os.remove(target_img)


if __name__ == "__main__":
    unittest.main()
