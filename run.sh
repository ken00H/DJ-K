#!/usr/bin/env bash
# DJ Jamal launcher. AI: llama.cpp :8080 → Ollama → OpenAI (auto).
# Usage: ./run.sh          → terminal REPL
#        ./run.sh web      → web UI on http://127.0.0.1:8090
cd "$(dirname "$0")"
case "${1:-}" in
  web) exec python3 dj/web.py ;;
  *)   exec python3 dj/main.py ;;
esac
