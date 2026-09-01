"""
Core package for AI Agent Thersites.
"""
from core.engine import run_agent_inner_loop
from core.contract import SYSTEM_CONTRACT
from core.parsers import extract_fuzzy_json, clean_html_to_text, extract_structured_feed
from core.database import (
    init_db, create_session, get_recent_sessions, set_active_session,
    get_or_create_active_session, add_message, toggle_message_pin,
    get_pinned_messages, get_rolling_messages, get_all_messages,
    add_scratch_message, execute_user_sql_query, cleanup_test_data,
    delete_message, save_clue, delete_clue, get_all_clues, get_clues_by_type
)
from core.warden import (
    inspect_and_authorize, enforce_single_action_rule, validate_url,
    validate_write_path, validate_sql_query, validate_image_path,
    WardenViolation
)

__all__ = [
    "run_agent_inner_loop",
    "SYSTEM_CONTRACT",
    "extract_fuzzy_json",
    "clean_html_to_text",
    "extract_structured_feed",
    "init_db",
    "create_session",
    "get_recent_sessions",
    "set_active_session",
    "get_or_create_active_session",
    "add_message",
    "toggle_message_pin",
    "get_pinned_messages",
    "get_rolling_messages",
    "get_all_messages",
    "add_scratch_message",
    "execute_user_sql_query",
    "cleanup_test_data",
    "delete_message",
    "save_clue",
    "delete_clue",
    "get_all_clues",
    "get_clues_by_type",
    "inspect_and_authorize",
    "enforce_single_action_rule",
    "validate_url",
    "validate_write_path",
    "validate_sql_query",
    "validate_image_path",
    "WardenViolation"
]
