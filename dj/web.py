"""Web UI: stdlib http.server serving one page + JSON API over the same modules."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dj import djbrain, library
from dj.main import enqueue_smart, generate_track
from dj.player import Player

INDEX_HTML = (Path(__file__).with_name("index.html")).read_text()
HISTORY = []


def make_handler(player, lib):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # quiet
            pass

        def do_GET(self):
            if self.path == "/":
                body = INDEX_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/state":
                self._json({"current": player.current,
                            "playing": player._playing(),
                            "queue": [t for _, t in player.queue]})
            else:
                self.send_error(404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")

            if self.path == "/api/chat":
                text = str(data.get("text", "")).strip()
                if not text:
                    return self._json({"error": "empty"}, 400)
                try:
                    brain = djbrain.think(text, tracks_hint=lib, history=HISTORY)
                except Exception as e:
                    return self._json({"reply": str(e), "action": "chat", "tracks": []})
                HISTORY.extend([{"role": "user", "content": text},
                                {"role": "assistant", "content": brain["reply"]}])
                del HISTORY[:-6]
                try:
                    if brain["action"] == "stop":
                        player.stop()
                    elif brain["action"] == "generate" and brain["tracks"]:
                        generate_track(player, brain["tracks"][0])  # status shows via queue
                    elif brain["action"] in ("play", "search", "queue", "playlist") and brain["tracks"]:
                        if brain["action"] in ("play", "search"):
                            player.stop()
                        enqueue_smart(player, lib, brain["tracks"])
                except ValueError as e:
                    brain["reply"] += f" (skipped: {e})"
                return self._json(brain)

            if self.path == "/api/cmd":
                cmd = data.get("cmd")
                {"skip": player.skip, "pause": player.pause,
                 "stop": player.stop}.get(cmd, lambda: None)()
                return self._json({"ok": True})

            self.send_error(404)

    return Handler


def serve(port=int(os.environ.get("DJ_WEB_PORT", "8090"))):
    lib = library.scan()
    player = Player()
    print(f"🎧 DJ Jamal web UI → http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), make_handler(player, lib)).serve_forever()


if __name__ == "__main__":
    serve()
