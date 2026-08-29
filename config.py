"""
Central Configuration Loader for AI Agent Thersites
Loads settings from config.json with environment variable overrides and CLI flags.
"""
import os
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_JSON_PATH = BASE_DIR / "config.json"

config_data = {}
if CONFIG_JSON_PATH.exists():
    try:
        with open(CONFIG_JSON_PATH, "r", encoding="utf-8-sig") as f:
            config_data = json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load config.json ({e}). Using defaults.")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", config_data.get("OLLAMA_BASE_URL", "http://localhost:11434"))
MODEL_NAME = os.environ.get("MODEL_NAME", config_data.get("MODEL_NAME", "qwen3.5:9b"))
KEEP_AI_ALIVE = os.environ.get("KEEP_AI_ALIVE", config_data.get("KEEP_AI_ALIVE", "5m"))
NUM_CTX = int(os.environ.get("NUM_CTX", config_data.get("NUM_CTX", 2048)))
ROLLING_BUFFER_CHAR_LIMIT = int(os.environ.get("ROLLING_BUFFER_CHAR_LIMIT", config_data.get("ROLLING_BUFFER_CHAR_LIMIT", 20000)))
PINNED_CONTEXT_CHAR_LIMIT = int(os.environ.get("PINNED_CONTEXT_CHAR_LIMIT", config_data.get("PINNED_CONTEXT_CHAR_LIMIT", 5000)))
MAX_INNER_LOOP_TURNS = int(os.environ.get("MAX_INNER_LOOP_TURNS", config_data.get("MAX_INNER_LOOP_TURNS", 5)))
URL_DOMAIN_WHITELIST = config_data.get("URL_DOMAIN_WHITELIST", ["nu.nl"])

VERBOSE = "--verbose" in sys.argv or os.environ.get("VERBOSE") == "1" or config_data.get("VERBOSE", False)

DB_PATH = BASE_DIR / "data" / "thersites.db"
SANDBOX_DIR = BASE_DIR / "sandbox"
SCRATCHPAD_PATH = BASE_DIR / "scratchpad.md"
STATIC_DIR = BASE_DIR / "static"
TESTS_DIR = BASE_DIR / "tests"
DOCS_DIR = BASE_DIR / "docs"
SCRIPTS_DIR = BASE_DIR / "scripts"
DATA_DIR = BASE_DIR / "data"

os.makedirs(SANDBOX_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
