"""DJ voice: optional piper TTS. Synthesizes to a temp wav, plays it through
the same validated mpv path — no extra player, no new hard dependency
(app runs stdlib-only when piper or the voice model is absent)."""
import atexit
import glob
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from . import mpvproc, settings

MAX_CHARS = 280
_live = []  # in-flight voice mpv processes (cleaned up on exit/quit)


def sweep_temp_audio():
    """Delete last run's orphaned temp audio (voice wavs, generated tracks and
    their IPC sockets) — left behind when quit paths hard-exit mid-playback.
    # ponytail: startup sweep only; a wav generated this session lives until
    the next restart (reaping after playback would need player coupling)"""
    for pat in ("djk-tts-*.wav", "djgen-*.wav", "djjamal-*.sock"):
        for p in glob.glob(os.path.join(tempfile.gettempdir(), pat)):
            try:
                os.unlink(p)
            except OSError:
                pass
            if not p.endswith(".sock"):  # tts/gen wavs keep their socket next to them
                try:
                    os.unlink(p + ".sock")
                except OSError:
                    pass


def stop_all():
    """Terminate any in-flight voice playback — used by quit paths and atexit."""
    for p in _live:
        try:
            p.terminate()
        except Exception:
            pass
    _live.clear()


atexit.register(stop_all)


def _voice():
    return Path(os.path.expanduser(settings.resolve("tts_voice")))


def available():
    """True when TTS can run: enabled, piper binary and voice model present."""
    v = _voice()
    return (settings.tts() and v.is_file()
            and shutil.which("piper") is not None)


def clip(text):
    """Collapse whitespace and cap at MAX_CHARS, ending at a sentence or word
    boundary. Pure function — unit-tested."""
    text = " ".join(text.split())
    if len(text) <= MAX_CHARS:
        return text
    cut = text[:MAX_CHARS]
    for sep in (". ", "! ", "? "):
        i = cut.rfind(sep)
        if i > MAX_CHARS // 4:
            return cut[:i + 1]
    return cut[:cut.rfind(" ")] + "…"


def speak(text):
    """Synthesize and start playing. Returns the mpv Popen (caller waits and
    un-ducks) or None if unavailable/failed. Blocks during synthesis only."""
    text = clip(text)
    if not text or not available():
        return None
    fd, wav = tempfile.mkstemp(suffix=".wav", prefix="djk-tts-")
    os.close(fd)
    try:
        subprocess.run(
            ["piper", "-m", str(_voice()), "-f", wav],
            input=text.encode(), stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, check=True, timeout=120)
        sock = wav + ".sock"  # dummy path; mpv creates it
        proc = mpvproc.launch(sock, 100, wav)
    except Exception:
        try:
            os.unlink(wav)
        except OSError:
            pass
        return None
    _live.append(proc)
    threading.Thread(target=_reap, args=(proc, wav, sock), daemon=True).start()
    return proc


def _reap(proc, wav, sock):
    """Delete the temp wav (and its IPC socket) once mpv is done with it."""
    try:
        proc.wait(timeout=120)
    except Exception:
        proc.terminate()
    for p in (wav, sock):
        try:
            os.unlink(p)
        except OSError:
            pass
    if proc in _live:
        _live.remove(proc)
