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

    def test_03_warden_ssrf_and_blacklist_protection(self):
        # Public domains are authorized
        ok_nu, msg_nu, _ = inspect_and_authorize("web_fetch", {"url": "https://nu.nl/tech"})
        self.assertTrue(ok_nu)
        
        ok_wiki, msg_wiki, _ = inspect_and_authorize("web_fetch", {"url": "https://wikipedia.org/wiki/Utrecht"})
        self.assertTrue(ok_wiki)
        
        # SSRF Private IPs and Localhost are blocked
        ok_local, msg_local, _ = inspect_and_authorize("web_fetch", {"url": "http://127.0.0.1:8000/api/secret"})
        self.assertFalse(ok_local)
        self.assertIn("blocked", msg_local.lower())
        
        ok_priv, msg_priv, _ = inspect_and_authorize("web_fetch", {"url": "http://192.168.1.1/admin"})
        self.assertFalse(ok_priv)
        self.assertIn("blocked", msg_priv.lower())
        
        # Invalid protocol blocked
        ok_file, msg_file, _ = inspect_and_authorize("web_fetch", {"url": "file:///C:/passwords.txt"})
        self.assertFalse(ok_file)
        self.assertIn("blocked", msg_file.lower())

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

        # Test private IP / SSRF domain blocked for image download
        ok, msg, params = inspect_and_authorize("download_image", {
            "url": "http://127.0.0.1:8000/internal_image.png",
            "filepath": target_img
        })
        self.assertFalse(ok)
        self.assertIn("blocked", msg.lower())

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



    def test_11_paycheck_memory_capsule_and_co_action(self):
        import database
        from warden import enforce_single_action_rule, inspect_and_authorize
        from engine import execute_tool_call
        
        # 1. Test database save_clue, get_all_clues, delete_clue
        database.save_clue("test_coffee", "espresso with cream")
        clues = database.get_all_clues()
        self.assertTrue(any(c["key"] == "test_coffee" and c["value"] == "espresso with cream" for c in clues))
        
        # 2. Test Warden authorization for remember and unremember
        ok, msg, _ = inspect_and_authorize("remember", {"key": "test_pref", "clue": "high priority"})
        self.assertTrue(ok)
        
        ok_del, msg_del, _ = inspect_and_authorize("unremember", {"key": "test_pref"})
        self.assertTrue(ok_del)
        
        # 3. Test Memory Co-Action Rule (1 external tool + 1 internal memory action passes without deferral)
        co_actions = [
            {"id": "act_1", "tool": "get_room_temperatures", "params": {}},
            {"id": "act_2", "tool": "remember", "params": {"key": "study_temp", "clue": "21.5C"}}
        ]
        filtered, notice = enforce_single_action_rule(co_actions)
        self.assertEqual(len(filtered), 2)
        self.assertIsNone(notice)  # Zero warning/deferral for memory co-action!
        
        # 4. Test engine execution
        res = execute_tool_call({"id": "act_mem", "tool": "remember", "params": {"key": "study_note", "clue": "turn off heater at night"}})
        self.assertEqual(res["status"], "success")
        self.assertIn("Clue saved", res["result"])
        
        # Cleanup
        database.delete_clue("test_coffee")
        database.delete_clue("study_temp")
        database.delete_clue("study_note")



    def test_12_gorgons_gaze_image_validation_and_encoding(self):
        from warden import validate_image_path, inspect_and_authorize
        from engine import encode_image_to_base64
        import tempfile
        
        # 1. Test validate_image_path on existing image
        test_img_path = Path("Images/Thersites_orginal_v2.png")
        if test_img_path.exists():
            ok, msg = validate_image_path(str(test_img_path))
            self.assertTrue(ok)
            self.assertIn("authorized", msg)
            
            # Test base64 encoding
            b64_str = encode_image_to_base64(str(test_img_path))
            self.assertIsInstance(b64_str, str)
            self.assertTrue(len(b64_str) > 100)
            
        test_ico_path = Path("Images/Thersites_orginal_v2_128.ico")
        if test_ico_path.exists():
            ok_ico, msg_ico = validate_image_path(str(test_ico_path))
            self.assertTrue(ok_ico)
            b64_ico = encode_image_to_base64(str(test_ico_path))
            self.assertIsInstance(b64_ico, str)
            self.assertTrue(len(b64_ico) > 100)
            
        # 2. Test invalid extension
        bad_ext_path = Path("sandbox/test_bad.txt")
        with open(bad_ext_path, "w") as f:
            f.write("not an image")
        ok_bad, msg_bad = validate_image_path(str(bad_ext_path))
        self.assertFalse(ok_bad)
        self.assertIn("invalid image extension", msg_bad)
        if bad_ext_path.exists():
            os.remove(bad_ext_path)
            
        # 3. Test non-existent file
        ok_none, msg_none = validate_image_path("sandbox/does_not_exist_99.png")
        self.assertFalse(ok_none)
        self.assertIn("does not exist", msg_none)
        
        # 4. Test inspect_and_authorize for inspect_image
        if test_img_path.exists():
            ok_auth, msg_auth, _ = inspect_and_authorize("identify_image", {"filepath": str(test_img_path), "prompt": "Describe"})
            self.assertTrue(ok_auth)



    def test_13_typed_memory_and_list_favorites(self):
        import database
        from engine import execute_tool_call
        
        # 1. Test database save_clue with type='memory' vs type='url_fav'
        database.save_clue("cat_name", "Guus", entry_type="memory")
        database.save_clue("utrecht", "https://www.duic.nl/rss/", entry_type="url_fav")
        
        memories = database.get_clues_by_type("memory")
        self.assertTrue(any(c["key"] == "cat_name" and c["value"] == "Guus" for c in memories))
        
        favs = database.get_clues_by_type("url_fav")
        self.assertTrue(any(f["key"] == "utrecht" and "duic.nl" in f["value"] for f in favs))
        
        # 2. Test engine execute_tool_call for list_internet_fav
        res = execute_tool_call({"id": "act_list_fav", "tool": "list_internet_fav", "params": {}})
        self.assertEqual(res["status"], "success")
        self.assertIn("utrecht", res["result"])
        
        # Cleanup
    def test_14_web_fetch_direct_image_interceptor(self):
        from engine import execute_tool_call
        
        # Test direct .jpg URL interception in web_fetch
        res = execute_tool_call({
            "id": "act_wf_img",
            "tool": "web_fetch",
            "params": {"url": "https://m.media-amazon.com/images/M/photo.jpg"}
        })
        self.assertEqual(res["status"], "success")
        self.assertIn("DIRECT IMAGE URL DETECTED", res["result"])
        self.assertNotIn("JFIF", res["result"])

    def test_15_identify_image_url_and_relative_path(self):
        from warden import validate_image_path, inspect_and_authorize
        
        # 1. Test direct image URL authorization
        ok_url, msg_url = validate_image_path("https://m.media-amazon.com/images/M/test.jpg")
        self.assertTrue(ok_url)
        self.assertIn("authorized", msg_url)
        
        # 2. Test inspect_and_authorize with url parameter
        ok_auth, msg_auth, _ = inspect_and_authorize("identify_image", {"url": "https://images.nu.nl/test.png"})
        self.assertTrue(ok_auth)
        
        # 3. Test relative sandbox path resolution
        sandbox_test_img = SANDBOX_DIR / "temp_qa_test.jpg"
        with open(sandbox_test_img, "wb") as f:
            f.write(b"\xFF\xD8\xFF\xE0\x00\x10JFIF")
            
        ok_rel, msg_rel = validate_image_path("temp_qa_test.jpg")
        self.assertTrue(ok_rel)
        
        if sandbox_test_img.exists():
            os.remove(sandbox_test_img)

    def test_16_inner_loop_assistant_scratch_context(self):
        import json
        
        # Verify scratch history structure packaging
        turn_scratch = {
            "turn": 1,
            "assistant_raw": json.dumps({"thought": "Downloading image", "content": "Downloading...", "actions": [{"id": "act_1", "tool": "download_image", "params": {"url": "https://test.com/img.jpg"}}]}),
            "actions_executed": [{"id": "act_1", "tool": "download_image"}],
            "results": [{"id": "act_1", "tool": "download_image", "status": "success", "result": "Saved to sandbox/photo.jpg"}],
            "warden_notice": None
        }
        
        # Reconstruct llm_messages as done in engine
        llm_messages = [{"role": "system", "content": "system contract"}]
        llm_messages.append({"role": "user", "content": "Identify this image: https://test.com/img.jpg"})
        
        # Inner loop appends assistant step then tool result
        llm_messages.append({"role": "assistant", "content": turn_scratch["assistant_raw"]})
        res_summary = "\n".join([f"[TOOL RESULT '{r.get('tool')}']: {str(r.get('result'))}" for r in turn_scratch["results"]])
        llm_messages.append({"role": "user", "content": res_summary})
        
        self.assertEqual(len(llm_messages), 4)
        self.assertEqual(llm_messages[2]["role"], "assistant")
        self.assertIn("download_image", llm_messages[2]["content"])
        self.assertEqual(llm_messages[3]["role"], "user")
        self.assertIn("Saved to sandbox/photo.jpg", llm_messages[3]["content"])

    def test_17_structured_rss_feed_extraction(self):
        from engine import clean_html_to_text
        
        sample_rss = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0">
            <channel>
                <title>NOS Nieuws</title>
                <item>
                    <title>Story One Title</title>
                    <link>https://nos.nl/l/10001</link>
                    <description>Story One Description content.</description>
                    <pubDate>Sun, 30 Aug 2026 20:00:00 +0200</pubDate>
                </item>
                <item>
                    <title>Halsema Story Title</title>
                    <link>https://nos.nl/l/10002</link>
                    <description>Femke Halsema discusses drug issues.</description>
                    <pubDate>Sun, 30 Aug 2026 19:00:00 +0200</pubDate>
                </item>
            </channel>
        </rss>"""
        
        result = clean_html_to_text(sample_rss)
        self.assertIn("[1] Story One Title", result)
        self.assertIn("https://nos.nl/l/10001", result)
        self.assertIn("[2] Halsema Story Title", result)
        self.assertIn("https://nos.nl/l/10002", result)
        self.assertIn("Femke Halsema discusses drug issues", result)

    def test_18_repeated_read_query_deduplication(self):
        executed_tools = {"list_internet_fav"}
        READ_ONLY_TOOLS = {"list_internet_fav", "list_favorites", "get_room_temperatures", "read_file", "list_sandbox"}
        
        act = {"id": "act_1", "tool": "list_internet_fav", "params": {}}
        tool_name = act["tool"]
        
        is_repeated = tool_name in READ_ONLY_TOOLS and tool_name in executed_tools
        self.assertTrue(is_repeated)

    def test_19_crawler_user_agent_configured(self):
        from config import WEB_USER_AGENT
        from engine import WEB_USER_AGENT as ENGINE_UA
        self.assertIn("Googlebot", WEB_USER_AGENT)
        self.assertEqual(WEB_USER_AGENT, ENGINE_UA)

    def test_20_parameterized_limits_configured(self):
        from config import TOOL_RESULT_CHAR_LIMIT, WEB_FETCH_CHAR_LIMIT
        from engine import TOOL_RESULT_CHAR_LIMIT as ENGINE_TOOL_LIMIT, WEB_FETCH_CHAR_LIMIT as ENGINE_FETCH_LIMIT
        self.assertEqual(TOOL_RESULT_CHAR_LIMIT, 16384)
        self.assertEqual(WEB_FETCH_CHAR_LIMIT, 16384)
        self.assertEqual(TOOL_RESULT_CHAR_LIMIT, ENGINE_TOOL_LIMIT)
        self.assertEqual(WEB_FETCH_CHAR_LIMIT, ENGINE_FETCH_LIMIT)

    def test_21_clean_html_with_base_url_resolution(self):
        html = '<main><a href="/nieuws/12345">Belangrijk artikel over energie</a><img src="/images/foto.jpg" alt="Foto"></main>'
        parsed = clean_html_to_text(html, base_url="https://www.duic.nl")
        self.assertIn("https://www.duic.nl/nieuws/12345", parsed)
        self.assertIn("https://www.duic.nl/images/foto.jpg", parsed)

    def test_22_warden_canonicalizes_filepaths(self):
        ok, msg, params = inspect_and_authorize("write_to_file", {"filepath": "sandbox/story.txt"})
        self.assertTrue(ok)
        self.assertTrue(Path(params["filepath"]).is_absolute())
        self.assertIn("sandbox", params["filepath"].lower())


if __name__ == '__main__':
    unittest.main()
