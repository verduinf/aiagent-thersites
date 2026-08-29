@echo off
echo ============================================================
echo   AI Agent Thersites - Local Server Launcher
echo   Model: Qwen3-9B (Ollama)
echo   URL: http://127.0.0.1:8000
echo ============================================================
echo.

echo Terminating any previous server process on port 8000...
powershell -Command "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo Opening Web UI in browser...
start http://127.0.0.1:8000

echo Starting FastAPI Server (Verbose Mode: Enabled)...
python server.py --verbose

pause
