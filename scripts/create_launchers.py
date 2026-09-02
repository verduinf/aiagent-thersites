"""
Creates launcher batch files and .lnk shortcuts for C:\Dev\ai-chatbot
"""
import os
import shutil
from pathlib import Path

DEST_DIR = Path(r"C:\Dev\ai-chatbot")
SRC_DIR = Path(r"C:\Dev\aiagent-thersites")

def main():
    # 1. Copy Images directory if present
    if (SRC_DIR / "Images").exists():
        shutil.copytree(SRC_DIR / "Images", DEST_DIR / "Images", dirs_exist_ok=True)
        print("[OK] Images copied to ai-chatbot")

    # 2. Write run_server.cmd
    run_normal = """@echo off
echo ============================================================
echo   AI Chatbot - Local Server Launcher
echo   Model: Local Ollama (Port 8080)
echo   URL: http://127.0.0.1:8080
echo ============================================================
echo.

echo Terminating any previous server process on port 8080...
powershell -Command "Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo Opening Web UI in browser...
start http://127.0.0.1:8080

echo Starting FastAPI Server...
python server.py

pause
"""
    (DEST_DIR / "run_server.cmd").write_text(run_normal, encoding="utf-8")
    print("[OK] run_server.cmd written")

    # 3. Write run_server verbose.cmd
    run_verbose = """@echo off
echo ============================================================
echo   AI Chatbot - Local Server Launcher (VERBOSE)
echo   Model: Local Ollama (Port 8080)
echo   URL: http://127.0.0.1:8080
echo ============================================================
echo.

echo Terminating any previous server process on port 8080...
powershell -Command "Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo Opening Web UI in browser...
start http://127.0.0.1:8080

echo Starting FastAPI Server (Verbose)...
python server.py --verbose

pause
"""
    (DEST_DIR / "run_server verbose.cmd").write_text(run_verbose, encoding="utf-8")
    print("[OK] run_server verbose.cmd written")

    # 4. Update server.py with --verbose handler
    server_file = DEST_DIR / "server.py"
    if server_file.exists():
        content = server_file.read_text(encoding="utf-8")
        target = 'if __name__ == "__main__":\n    kill_existing_port_process(port=PORT)\n    import uvicorn\n    uvicorn.run("server:app", host="127.0.0.1", port=PORT, reload=True)'
        replacement = 'if __name__ == "__main__":\n    import sys\n    verbose = "--verbose" in sys.argv\n    kill_existing_port_process(port=PORT)\n    import uvicorn\n    log_lvl = "debug" if verbose else "info"\n    if verbose:\n        print("[AI Chatbot] Verbose debug logging active.")\n    uvicorn.run("server:app", host="127.0.0.1", port=PORT, reload=True, log_level=log_lvl)'
        if target in content:
            content = content.replace(target, replacement)
            server_file.write_text(content, encoding="utf-8")
            print("[OK] server.py updated with --verbose flag handler")

if __name__ == "__main__":
    main()
