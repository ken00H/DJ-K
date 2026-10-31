"""mpv player wrapper: queue, playback, IPC control, crossfade via volume ramp."""
import json
import os
import secrets
import socket
import tempfile
import threading
import time

from . import beatmatch, mpvproc

FADE_SECS = 2.5
# ponytail: crossfade is volume-ramp overlap; tempo matching via beatmatch.py,
# true beat-phase alignment (start on the beat) needs beat-grid data — future
CROSSFADE = os.environ.get("DJ_CROSSFADE", "1") == "1"
WINDOWS = os.name == "nt"


class Player:
    def __init__(self, on_track_start=None):
        self.queue = []          # list of (source, title) — source: file path or URL
        self.proc = None
        self.sock_path = None
        self.current = None
        self.current_source = None  # path/URL of current track (for beatmatch)
        self.on_track_start = on_track_start
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
    def _transition_speed(self, new_source):
        """Speed for an incoming local file to match the outgoing track's tempo.
        YouTube/uncached/absent-analysis cases return 1.0 (plain crossfade)."""
        if not beatmatch.available():
            return 1.0
        old_src = self.current_source
        if not (old_src and os.path.isfile(old_src) and os.path.isfile(new_source)):
            return 1.0
        return beatmatch.speed_for(beatmatch.cached_bpm(old_src),
                                   beatmatch.cached_bpm(new_source)) or 1.0

    def play_now(self, source, title=""):
        """Start source immediately (with crossfade if something is playing)."""
        with self._lock:
            speed = self._transition_speed(source)
            old_proc, old_sock = self.proc, self.sock_path
            self.proc, self.sock_path = self._spawn(source, speed=speed)
            self.current, self.current_source = title or source, source
        beatmatch.prewarm([s for s, _ in self.queue[:2]])  # warm next transition
        if old_proc and old_proc.poll() is None:
            if CROSSFADE:
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

    def duck(self, on):
        """Duck music volume to 25% (on=True) / back to 100% — used while the
        DJ voice speaks over the track."""
        self._ipc(self.sock_path, ["set_property", "volume", 25 if on else 100])

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
