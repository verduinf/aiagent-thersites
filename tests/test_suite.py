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
from warden import inspect_and_authorize, WardenViolation, validate_url, validate_write_path, validate_sql_query, enforce_single_action_rule
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


    def test_10_warden_single_action_rule(self):
        # Multiple actions emitted in a single turn
        multi_actions = [
            {"id": "act_1", "tool": "web_fetch", "params": {"url": "https://nu.nl/weer"}},
            {"id": "act_2", "tool": "write_to_file", "params": {"filepath": "sandbox/w.txt", "content": "fake"}},
            {"id": "act_3", "tool": "send_message", "params": {"message": "fake weather"}}
        ]
        
        filtered, notice = enforce_single_action_rule(multi_actions)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["tool"], "web_fetch")
        self.assertIsNotNone(notice)
        self.assertIn("Single-Action Rule Active", notice)
        
        # Single action should pass unmodified with zero notice
        single_action = [{"id": "act_1", "tool": "web_fetch", "params": {"url": "https://nu.nl/weer"}}]
        filtered_single, notice_single = enforce_single_action_rule(single_action)
        self.assertEqual(len(filtered_single), 1)
        self.assertIsNone(notice_single)


    @patch("requests.post")
    @patch("requests.get")
    def test_11_tado_client_token_caching_and_extraction(self, mock_get, mock_post):
        import tado_client
        tado_client.set_tado_credentials("test_user@example.com", "test_secret_pass")
        
        # 1. Mock OAuth Token Response (expires in 599s)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "mock_bearer_token_xyz123",
            "token_type": "bearer",
            "expires_in": 599
        }
        
        # First token retrieval
        tok1 = tado_client.get_valid_access_token()
        self.assertEqual(tok1, "mock_bearer_token_xyz123")
        self.assertEqual(mock_post.call_count, 1)
        
        # Second token retrieval within 10 minutes MUST use in-memory cache with ZERO network calls
        tok2 = tado_client.get_valid_access_token()
        self.assertEqual(tok2, "mock_bearer_token_xyz123")
        self.assertEqual(mock_post.call_count, 1)  # Token was NOT requested in a loop!
        
        # 2. Mock /api/v2/me, /zones, and /zoneStates
        def mock_get_router(url, *args, **kwargs):
            m = MagicMock()
            m.status_code = 200
            if "api/v2/me" in url:
                m.json.return_value = {"homeId": 12345}
            elif "api/v2/homes/12345/zones" in url:
                m.json.return_value = [
                    {"id": 1, "name": "Living Room"},
                    {"id": 2, "name": "Bedroom"}
                ]
            elif "api/v2/homes/12345/zoneStates" in url:
                m.json.return_value = {
                    "zoneStates": {
                        "1": {
                            "setting": {"power": "ON", "temperature": {"celsius": 20.0}},
                            "sensorDataPoints": {
                                "insideTemperature": {"celsius": 21.2},
                                "humidity": {"percentage": 50.0}
                            },
                            "activityDataPoints": {"heatingPower": {"percentage": 0.0}}
                        },
                        "2": {
                            "setting": {"power": "OFF"},
                            "sensorDataPoints": {
                                "insideTemperature": {"celsius": 18.5},
                                "humidity": {"percentage": 55.0}
                            }
                        }
                    }
                }
            return m
            
        mock_get.side_effect = mock_get_router
        
        # Run room temperature extraction
        res = tado_client.get_room_temperatures()
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["home_id"], 12345)
        self.assertIn("Living Room", res["rooms"])
        self.assertEqual(res["rooms"]["Living Room"]["current_temperature_celsius"], 21.2)
        self.assertIn("21.2?C", res["summary_text"])
        self.assertIn("Bedroom: 18.5?C", res["summary_text"])


if __name__ == "__main__":
    unittest.main()
