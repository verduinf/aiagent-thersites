@echo off
title AI Agent Thersites - Local Server
echo ============================================================
echo   AI Agent Thersites - Local Server Launcher
echo   Model: Qwen3-9B (Ollama)
echo   URL: http://127.0.0.1:8000
echo ============================================================
echo.
cd /d C:\Dev\aiagent-thersites
python server.py
pause
