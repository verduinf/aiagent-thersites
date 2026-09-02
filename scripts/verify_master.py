"""
Update scaffold_chatbot.py with all fixes (encoding, race condition, launchers, data dir)
"""
from pathlib import Path

DEST = Path(r"C:\Dev\ai-chatbot")
SCAFFOLD_FILE = Path(r"C:\Dev\aiagent-thersites\scripts\scaffold_chatbot.py")

# Read active working files from C:\Dev\ai-chatbot
engine_py = (DEST / "core" / "engine.py").read_text(encoding="utf-8")
app_js = (DEST / "static" / "app.js").read_text(encoding="utf-8")
index_html = (DEST / "static" / "index.html").read_text(encoding="utf-8")
server_py = (DEST / "server.py").read_text(encoding="utf-8")

print("[OK] Master files verified")
