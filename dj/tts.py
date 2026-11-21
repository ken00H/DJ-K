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

MAX_CHARS = 140  # one breath of radio talk, not a monologue
_live = []  # in-flight voice mpv processes (cleaned up on exit/quit)
_synth = []  # in-flight piper synthesis subprocesses (cleaned up on exit/quit)


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
    """Terminate any in-flight voice playback or synthesis — quit paths and atexit."""
    for procs in (_live, _synth):
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        procs.clear()


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


def speak(text, volume=None):
    """Synthesize and start playing at `volume` (default: the tts_volume
    setting). Returns the mpv Popen (caller waits and un-ducks) or None if
    unavailable/failed. Blocks during synthesis only."""
    text = clip(text)
    if not text or not available():
        return None
    if volume is None:
        volume = settings.tts_volume()
    fd, wav = tempfile.mkstemp(suffix=".wav", prefix="djk-tts-")
    os.close(fd)
    try:
        # ponytail: pacing constants, not settings — revisit only if the
        # chosen voice reads rushed or clipped by ear
        piper = subprocess.Popen(
            ["piper", "-m", str(_voice()), "-f", wav,
             "--length-scale", "1.1", "--sentence-silence", "0.5"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        _synth.append(piper)  # tracked so quit paths can reap a mid-synthesis child
        try:
            piper.communicate(input=text.encode(), timeout=120)
            if piper.returncode != 0:
                raise subprocess.CalledProcessError(piper.returncode, piper.args)
        except subprocess.TimeoutExpired:
            piper.kill()  # communicate(timeout) leaves the child running
            piper.wait()
            raise
        finally:
            if piper in _synth:
                _synth.remove(piper)
        sock = wav + ".sock"  # dummy path; mpv creates it
        proc = mpvproc.launch(sock, volume, wav, loudnorm=False)
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
