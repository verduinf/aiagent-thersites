"""
Central Configuration Loader for AI Agent Thersites
Loads settings from config.json with environment variable overrides and CLI flags.
"""
import os
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    try:
        with open(ENV_PATH, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k not in os.environ:
                        os.environ[k] = v
    except Exception as e:
        print(f"Warning: Failed to load .env ({e})")

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
MAX_INNER_LOOP_TURNS = int(os.environ.get("MAX_INNER_LOOP_TURNS", config_data.get("MAX_INNER_LOOP_TURNS", 8)))
AI_TEMPERATURE = float(os.environ.get("AI_TEMPERATURE", config_data.get("AI_TEMPERATURE", 0.3)))
URL_DOMAIN_BLACKLIST = config_data.get("URL_DOMAIN_BLACKLIST", ["localhost", "127.0.0.1", "0.0.0.0", "router.local", "fritz.box", "routerlogin.net", "192.168.1.1", "192.168.0.1"])
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY", config_data.get("PUSHOVER_USER_KEY", ""))
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN", os.environ.get("PUSHOVER_API", config_data.get("PUSHOVER_API_TOKEN", "")))
PUSHOVER_EMAIL = os.environ.get("PUSHOVER_EMAIL", config_data.get("PUSHOVER_EMAIL", ""))
VISION_MODEL_NAME = os.environ.get("VISION_MODEL_NAME", config_data.get("VISION_MODEL_NAME", "qwen2.5vl:7b"))
VISION_NUM_CTX = int(os.environ.get("VISION_NUM_CTX", config_data.get("VISION_NUM_CTX", 2048)))


VERBOSE = "--verbose" in sys.argv or os.environ.get("VERBOSE") == "1" or config_data.get("VERBOSE", False)

DB_PATH = BASE_DIR / "data" / "thersites.db"
SANDBOX_DIR = BASE_DIR / "sandbox"
UPLOADS_DIR = SANDBOX_DIR / "uploads"
SCRATCHPAD_PATH = BASE_DIR / "scratchpad.md"
STATIC_DIR = BASE_DIR / "static"
TESTS_DIR = BASE_DIR / "tests"
DOCS_DIR = BASE_DIR / "docs"
SCRIPTS_DIR = BASE_DIR / "scripts"
DATA_DIR = BASE_DIR / "data"

os.makedirs(SANDBOX_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
