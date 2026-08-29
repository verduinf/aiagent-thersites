"""
Config Settings for AI Agent Thersites
Loads settings from config.json with safe environment fallbacks.
"""
import os
import json
from pathlib import Path

# Paths
BASE_DIR = Path("C:/Dev/aiagent-thersites").resolve()
DOCS_DIR = BASE_DIR / "docs"
SCRIPTS_DIR = BASE_DIR / "scripts"
STATIC_DIR = BASE_DIR / "static"
TESTS_DIR = BASE_DIR / "tests"
DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)
TESTS_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "thersites.db"

# Sandbox Enclosure Path
SANDBOX_DIR = BASE_DIR / "sandbox"
SANDBOX_DIR.mkdir(exist_ok=True)
SCRATCHPAD_PATH = BASE_DIR / "scratchpad.md"

# Load config.json
CONFIG_JSON_PATH = BASE_DIR / "config.json"
config_data = {}
if CONFIG_JSON_PATH.exists():
    try:
        with open(CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
            config_data = json.load(f)
    except Exception:
        pass

# LLM & Ollama Settings
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", config_data.get("OLLAMA_BASE_URL", "http://localhost:11434"))
MODEL_NAME = os.getenv("OLLAMA_MODEL", config_data.get("MODEL_NAME", "qwen3.5:9b"))
KEEP_AI_ALIVE = os.getenv("KEEP_AI_ALIVE", config_data.get("KEEP_AI_ALIVE", "5m"))
NUM_CTX = int(os.getenv("NUM_CTX", config_data.get("NUM_CTX", 8192)))

# Context & Telemetry Limits
ROLLING_BUFFER_CHAR_LIMIT = int(config_data.get("ROLLING_BUFFER_CHAR_LIMIT", 20000))
PINNED_CONTEXT_CHAR_LIMIT = int(config_data.get("PINNED_CONTEXT_CHAR_LIMIT", 5000))
MAX_INNER_LOOP_TURNS = int(config_data.get("MAX_INNER_LOOP_TURNS", 5))

# Security Whitelists
URL_DOMAIN_WHITELIST = config_data.get("URL_DOMAIN_WHITELIST", ["nu.nl"])
