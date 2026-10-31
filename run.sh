#!/usr/bin/env bash
# DJ-K launcher. AI: llama.cpp :8080 → Ollama → OpenAI (auto).
# Usage: ./run.sh                → terminal REPL
#        ./run.sh web            → web UI on http://127.0.0.1:8090
#        ./run.sh desktop        → web UI + open the browser (app-grid entry)
#        ./run.sh install-desktop→ register icon + app-grid entry (~/.local)
cd "$(dirname "$0")"
case "${1:-}" in
  web)      exec python3 dj/web.py ;;
  desktop)  python3 dj/web.py & sleep 1; xdg-open "http://127.0.0.1:${DJ_WEB_PORT:-8090}" >/dev/null 2>&1; wait ;;
  install-desktop)
    mkdir -p ~/.local/share/icons/hicolor/scalable/apps ~/.local/share/applications
    cp assets/djk.svg ~/.local/share/icons/hicolor/scalable/apps/djk.svg
    printf '%s\n' \
      '[Desktop Entry]' \
      'Type=Application' \
      'Name=DJ-K' \
      'Comment=Personal AI DJ' \
      "Exec=\"$(pwd)/run.sh\" desktop" \
      'Icon=djk' \
      'Terminal=false' \
      'Categories=AudioVideo;Audio;Player;' \
      > ~/.local/share/applications/djk.desktop
    command -v desktop-file-validate >/dev/null && desktop-file-validate ~/.local/share/applications/djk.desktop
    echo "installed: app-grid entry 'DJ-K' + icon" ;;
  *)        exec python3 dj/main.py ;;
esac
