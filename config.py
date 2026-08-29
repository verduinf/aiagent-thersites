"""
Config Settings for AI Agent Thersites
"""
import os
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

# LLM & Ollama Settings
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen3:9b")
FALLBACK_MODEL_NAME = os.getenv("OLLAMA_FALLBACK_MODEL", "qwen2.5:7b")

# Context & Telemetry Limits
ROLLING_BUFFER_CHAR_LIMIT = 20000
PINNED_CONTEXT_CHAR_LIMIT = 5000
MAX_INNER_LOOP_TURNS = 5

# Security Whitelists
URL_DOMAIN_WHITELIST = [
    "localhost",
    "127.0.0.1",
    "python.org",
    "docs.python.org",
    "pypi.org",
    "github.com",
    "raw.githubusercontent.com",
    "openrouter.ai"
]
