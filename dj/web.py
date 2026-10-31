"""Web UI: stdlib http.server serving one page + JSON API over the same modules."""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dj import djbrain, library, mpris, settings, tray, tts
from dj.main import enqueue_smart, generate_track
from dj.player import Player

INDEX_HTML = (Path(__file__).with_name("index.html")).read_text()
HISTORY = []


def cross_site(headers):
    """CSRF guard for POSTs: True when the request declares another origin.
    Header-less clients (curl, tests) pass; browsers always send Origin or
    Sec-Fetch-Site on cross-site requests."""
    site = headers.get("Sec-Fetch-Site")
    if site and site not in ("same-origin", "none"):
        return True
    origin = headers.get("Origin")
    if origin:
        host = origin.split("//", 1)[-1].rsplit(":", 1)[0].strip("[]")
        if not origin.startswith("http://") or host not in ("127.0.0.1", "localhost", "::1"):
            return True
    return False


def make_handler(player, state):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self):
            # DNS-rebinding guard: only our own loopback origin may talk to us
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            return host in ("127.0.0.1", "localhost", "[::1]", "::1")

        def log_message(self, *a):  # quiet
            pass

        def do_GET(self):
            if not self._host_ok():
                return self._json({"error": "bad host"}, 403)
            if self.path == "/":
                body = INDEX_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/state":
                st = player.status()
                st["source_local"] = settings.source_local()
                self._json(st)
            elif self.path == "/api/library":
                tracks = [] if not settings.source_local() else state["library"]
                self._json([{"name": t["name"], "path": t["path"]} for t in tracks])
            elif self.path == "/api/history":
                self._json(HISTORY)
            elif self.path == "/api/settings":
                snap = settings.snapshot()
                snap["openai_api_key"] = settings.mask(snap["openai_api_key"])
                self._json(snap)
            else:
                self.send_error(404)

        def do_POST(self):
            if not self._host_ok():
                return self._json({"error": "bad host"}, 403)
            if cross_site(self.headers):
                return self._json({"error": "cross-site request blocked"}, 403)
            try:
                length = max(0, int(self.headers.get("Content-Length", 0)))
            except ValueError:
                length = 0
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._json({"error": "malformed JSON"}, 400)

            if self.path == "/api/chat":
                text = str(data.get("text", "")).strip()
                if not text:
                    return self._json({"error": "empty"}, 400)
                try:
                    brain = djbrain.think(text, tracks_hint=state["library"],
                                          history=HISTORY)
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
                        enqueue_smart(player, state["library"], brain["tracks"])
                except ValueError as e:
                    brain["reply"] += f" (skipped: {e})"
                return self._json(brain)

            if self.path == "/api/settings":
                # partial update: live toggles apply now; other keys restart
                masked_out = str(data.get("openai_api_key", ""))
                if "…" in masked_out:  # unchanged masked key sent back
                    data.pop("openai_api_key", None)
                changes = {k: v for k, v in data.items() if k in settings.SCHEMA}
                if not changes:
                    snap = settings.snapshot()
                    snap["openai_api_key"] = settings.mask(snap["openai_api_key"])
                    return self._json({"ok": True, "settings": snap,
                                       "restart_needed": []})
                try:
                    settings.update(changes)
                except (KeyError, TypeError, ValueError) as e:
                    return self._json({"error": f"invalid: {e}"}, 400)
                saved = settings.snapshot()
                saved["openai_api_key"] = settings.mask(saved["openai_api_key"])
                return self._json({"ok": True, "settings": saved,
                                   "restart_needed": [k for k in changes
                                                      if k in settings.RESTART_KEYS]})

            if self.path == "/api/cmd":
                cmd = data.get("cmd")
                if cmd == "volume":
                    try:
                        player.volume(int(data.get("value", 100)))
                    except (TypeError, ValueError):
                        return self._json({"error": "bad volume"}, 400)
                elif cmd == "seek":
                    try:
                        player.seek(float(data.get("value", 0)))
                    except (TypeError, ValueError):
                        return self._json({"error": "bad position"}, 400)
                elif cmd == "quit":
                    tts.stop_all()
                    player.stop()  # kill mpv now; exit after the reply flushes
                    threading.Timer(0.5, os._exit, (0,)).start()
                else:
                    {"skip": player.skip, "pause": player.pause,
                     "stop": player.stop}.get(cmd, lambda: None)()
                return self._json({"ok": True})

            if self.path == "/api/track":
                # play/queue a specific library track by path (validated in player)
                if not settings.source_local():
                    return self._json({"error": "local source disabled"}, 400)
                lib = state["library"]
                path = str(data.get("path", ""))
                mode = data.get("mode", "queue")
                if path not in {t["path"] for t in lib}:
                    return self._json({"error": "not in library"}, 400)
                try:
                    if mode == "play":
                        player.stop()
                    player.enqueue(path, next(t["name"] for t in lib if t["path"] == path))
                except ValueError as e:
                    return self._json({"error": str(e)}, 400)
                return self._json({"ok": True})

            if self.path == "/api/rescan":
                state["library"] = library.scan(force=True)
                return self._json({"ok": True, "count": len(state["library"])})

            self.send_error(404)

    return Handler


def serve(port=None):
    if port is None:
        port = settings.resolve("web_port")
    state = {"library": library.scan()}
    player = Player()
    mpris.start(player)  # desktop presence: media controls (no-op if no gi)
    tray.start(player, str(Path(__file__).resolve().parent.parent / "assets" / "djk.svg"))
    print(f"🎧 DJ-K web UI → http://127.0.0.1:{port}")
    try:
        ThreadingHTTPServer(("127.0.0.1", port),
                            make_handler(player, state)).serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        tts.stop_all()
        player.stop()


if __name__ == "__main__":
    serve()
