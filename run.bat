@echo off
rem DJ Jamal launcher (Windows). AI: llama.cpp :8080 - Ollama - OpenAI (auto).
rem Usage: run.bat        - terminal REPL
rem        run.bat web    - web UI on http://127.0.0.1:8090
cd /d "%~dp0"
if "%1"=="web" (python dj\web.py) else (python dj\main.py)
