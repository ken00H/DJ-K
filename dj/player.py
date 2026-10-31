"""mpv player wrapper: queue, playback, IPC control, crossfade via volume ramp."""
import json
import os
import secrets
import socket
import tempfile
import threading
import time

from . import beatmatch, mpvproc, settings

FADE_SECS = 2.5
# ponytail: crossfade is volume-ramp overlap; tempo matching via beatmatch.py,
# true beat-phase alignment (start on the beat) needs beat-grid data — future
WINDOWS = os.name == "nt"


class Player:
    def __init__(self, on_track_start=None):
        self.queue = []          # list of (source, title) — source: file path or URL
        self.proc = None
        self.sock_path = None
        self.current = None
        self.current_source = None  # path/URL of current track (for beatmatch)
        self.on_track_start = on_track_start
        self._pre_duck = 100
        self._lock = threading.RLock()
        threading.Thread(target=self._advance_loop, daemon=True).start()

    # --- mpv IPC -----------------------------------------------------------
    @staticmethod
    def _ipc(sock, cmd):
        if not sock:
            return
        try:
            if WINDOWS:
                # named pipe: open r+b, write, close (mpv handles short sessions)
                with open(sock, "r+b", buffering=0) as f:
                    f.write(json.dumps({"command": cmd}).encode() + b"\n")
            else:
                s = socket.socket(socket.AF_UNIX)
                s.settimeout(0.5)
                s.connect(sock)
                s.send(json.dumps({"command": cmd}).encode() + b"\n")
                s.close()
        except OSError:
            pass

    @staticmethod
    def _ipc_query(sock, cmd, timeout=1.0):
        """Send a command and read one JSON response line, or None."""
        if not sock:
            return None
        try:
            if WINDOWS:
                with open(sock, "r+b", buffering=0) as f:
                    f.write(json.dumps({"command": cmd}).encode() + b"\n")
                    data = f.readline()
            else:
                s = socket.socket(socket.AF_UNIX)
                s.settimeout(timeout)
                s.connect(sock)
                s.send(json.dumps({"command": cmd}).encode() + b"\n")
                data = b""
                while not data.endswith(b"\n"):
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                s.close()
            return json.loads(data.split(b"\n")[0])
        except (OSError, ValueError):
            return None

    @staticmethod
    def _sock_ready(sock):
        """True once mpv is listening. POSIX: socket file exists. Windows:
        named pipe accepts a connection (os.path.exists is unreliable there)."""
        if not WINDOWS:
            return os.path.exists(sock)
        try:
            with open(sock, "r+b", buffering=0):
                return True
        except OSError:
            return False

    @staticmethod
    def _new_sock_name():
        if WINDOWS:
            return f"\\\\.\\pipe\\djjamal-{secrets.token_hex(8)}"
        runtime = os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir())
        return os.path.join(runtime, f"djjamal-{secrets.token_hex(8)}.sock")

    @staticmethod
    def _spawn(source, start_volume=100, speed=1.0):
        # unpredictable pipe/socket name (mkstemp would pre-create the file)
        sock = Player._new_sock_name()
        p = mpvproc.launch(sock, start_volume, source, speed)
        for _ in range(50):
            if Player._sock_ready(sock):
                break
            time.sleep(0.1)
        if p.poll() is not None:  # mpv died before creating its socket (bad source)
            Player._unlink(sock)
            raise ValueError(f"mpv exited immediately: {source!r}")
        return p, sock

    @staticmethod
    def _unlink(sock):
        try:
            os.unlink(sock)
        except OSError:  # Windows named pipes have no file to remove
            pass

    @staticmethod
    def _fade_and_kill(proc, sock, secs=FADE_SECS):
        steps = 10
        for i in range(steps, -1, -1):
            if proc.poll() is not None:
                break
            Player._ipc(sock, ["set_property", "volume", max(0, int(100 * i / steps))])
            time.sleep(secs / steps)
        proc.terminate()
        Player._unlink(sock)

    # --- public API --------------------------------------------------------
    def _transition_speed(self, new_source, bm_available):
        """Speed for an incoming local file to match the outgoing track's tempo.
        YouTube/uncached/absent-analysis cases return 1.0 (plain crossfade)."""
        if not bm_available:
            return 1.0
        old_src = self.current_source
        if not (old_src and os.path.isfile(old_src) and os.path.isfile(new_source)):
            return 1.0
        return beatmatch.speed_for(beatmatch.cached_bpm(old_src),
                                   beatmatch.cached_bpm(new_source)) or 1.0

    def play_now(self, source, title=""):
        """Start source immediately (with crossfade if something is playing)."""
        bm_available = beatmatch.available()  # probe outside the lock (cold venv: slow)
        with self._lock:
            speed = self._transition_speed(source, bm_available)
            old_proc, old_sock = self.proc, self.sock_path
            self.proc, self.sock_path = self._spawn(source, speed=speed)
            self.current, self.current_source = title or source, source
        beatmatch.prewarm([s for s, _ in self.queue[:2]])  # warm next transition
        if old_proc and old_proc.poll() is None:
            if settings.crossfade():
                threading.Thread(target=self._fade_and_kill,
                                 args=(old_proc, old_sock), daemon=True).start()
            else:
                old_proc.terminate()
        self._notify()

    def enqueue(self, source, title=""):
        self.queue.append((source, title or source))
        if not self._playing():
            self._pop_and_play()

    def skip(self):
        with self._lock:
            if self.queue:
                try:
                    self._pop_and_play(force=True)
                except ValueError as e:
                    print(f"skipped a bad source: {e}")
            elif self._playing():
                self.stop()

    def stop(self):
        with self._lock:
            self.queue.clear()
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
            self.proc, self.current, self.current_source = None, None, None

    def pause(self):
        self._ipc(self.sock_path, ["cycle", "pause"])

    def volume(self, vol=None):
        """Set volume (0-100) when given; return current volume or None."""
        if vol is not None:
            self._ipc(self.sock_path, ["set_property", "volume",
                                       max(0, min(100, int(vol)))])
            return None
        r = self._ipc_query(self.sock_path, ["get_property", "volume"])
        return r.get("data") if r and r.get("error") == "success" else None

    def seek(self, pos):
        if pos is not None:
            self._ipc(self.sock_path, ["set_property", "time-pos",
                                       max(0.0, float(pos))])

    def status(self):
        """Rich state for UIs: adds volume/position/duration/bpm/paused to the basics."""
        r = self._ipc_query(self.sock_path, ["get_property", "time-pos"])
        pos = r.get("data") if r and r.get("error") == "success" else None
        r = self._ipc_query(self.sock_path, ["get_property", "duration"])
        dur = r.get("data") if r and r.get("error") == "success" else None
        r = self._ipc_query(self.sock_path, ["get_property", "pause"])
        paused = bool(r.get("data")) if r and r.get("error") == "success" else False
        bpm = beatmatch.cached_bpm(self.current_source) \
            if self.current_source and os.path.isfile(self.current_source) else None
        return {"current": self.current,
                "playing": self._playing(),
                "paused": paused,
                "queue": [t for _, t in self.queue],
                "volume": self.volume(),
                "pos": pos,
                "duration": dur,
                "bpm": round(bpm, 1) if bpm else None}

    def duck(self, on):
        """Duck music volume to 25% (on=True) / back to the pre-duck level —
        used while the DJ voice speaks over the track."""
        if on:
            self._pre_duck = self.volume() or 100
            self._ipc(self.sock_path, ["set_property", "volume", 25])
        else:
            self._ipc(self.sock_path, ["set_property", "volume", self._pre_duck])

    def _playing(self):
        return self.proc is not None and self.proc.poll() is None

    def _pop_and_play(self, force=False):
        with self._lock:
            # guard: if a track just started (advance loop vs enqueue race), leave the queue alone
            if not self.queue or (self._playing() and not force):
                return
            source, title = self.queue.pop(0)
        if source.startswith("ytq:"):
            # resolve at play time: googleaudio URLs expire (~6h) if pre-resolved
            # ponytail: resolve outside the lock (stop() stays responsive); a concurrent
            # skip can briefly start its track before this one replaces it — accepted
            try:
                source, title = mpvproc.resolve_youtube(source[4:])
            except Exception as e:
                print(f"yt resolve failed ({title}): {e}")
                return self._pop_and_play(force)  # try the next queued track
        self.play_now(source, title)

    def _notify(self):
        if self.on_track_start:
            try:
                self.on_track_start(self.current)
            except Exception:
                pass

    def _advance_loop(self):
        while True:
            time.sleep(1.0)
            with self._lock:
                dead = self.proc is not None and self.proc.poll() is not None
            if dead and self.queue:
                try:
                    self._pop_and_play()
                except ValueError as e:
                    print(f"skipped a bad source: {e}")  # move on to next track on next tick
