"""DJ voice: optional piper TTS. Synthesizes to a temp wav, plays it through
the same validated mpv path — no extra player, no new hard dependency
(app runs stdlib-only when piper or the voice model is absent)."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import mpvproc, settings

MAX_CHARS = 280


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
    fd, wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        subprocess.run(
            ["piper", "-m", str(_voice()), "-f", wav],
            input=text.encode(), stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, check=True, timeout=120)
        sock = wav + ".sock"  # dummy path; mpv creates and we clean it below
        return mpvproc.launch(sock, 100, wav)
    except Exception:
        try:
            os.unlink(wav)
        except OSError:
            pass
        return None
    # temp wav lives in /tmp until reboot — mpv may stream it lazily
