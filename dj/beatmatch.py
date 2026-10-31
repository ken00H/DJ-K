"""Beatmatch: tempo-matched crossfades. Optional — runs librosa beat tracking
in the generation venv as a subprocess (same pattern as musicgen.py); the app
stays stdlib-only. Local files only: YouTube URLs fall back to plain crossfade."""
import json
import os
import subprocess
import threading
from pathlib import Path

from . import musicgen, settings

CACHE = Path.home() / ".config" / "djjamal" / "bpm.json"
CLAMP = 0.10  # ±10% speed change; beyond that tempos are too far apart to match

# runs inside the venv: ffmpeg-decode first 60s to wav, librosa beat_track.
# Always routing through ffmpeg avoids per-format soundfile support gaps (m4a).
_SCRIPT = """
import os, subprocess, sys, tempfile
import librosa
src = sys.argv[1]
fd, wav = tempfile.mkstemp(suffix=".wav"); os.close(fd)
try:
    subprocess.run(["ffmpeg", "-v", "error", "-t", "60", "-i", src,
                    "-ac", "1", "-ar", "22050", wav, "-y"],
                   check=True, timeout=120,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    y, sr = librosa.load(wav, sr=None, mono=True)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    print(tempo.item() if hasattr(tempo, "item") else float(tempo))
finally:
    try:
        os.unlink(wav)
    except OSError:
        pass
"""

_avail = None
_avail_lock = threading.Lock()


def available():
    """True when the venv python imports librosa (probed once, cached)."""
    global _avail
    if not settings.beatmatch():
        return False
    with _avail_lock:
        if _avail is None:
            try:
                _avail = subprocess.run(
                    [str(musicgen.VENV_PY), "-c", "import librosa"],
                    timeout=60, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL).returncode == 0
            except (OSError, subprocess.SubprocessError):
                _avail = False
        return _avail


def _load_cache():
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def _save_cache(data):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data))


def analyze(path):
    """Detect BPM (float) via the venv subprocess, cache it, or None on failure.
    Takes seconds — call from a worker thread (see prewarm)."""
    try:
        r = subprocess.run([str(musicgen.VENV_PY), "-c", _SCRIPT, path],
                           capture_output=True, text=True, timeout=180)
        bpm = float(r.stdout.strip().splitlines()[-1])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None
    if not 30 <= bpm <= 300:  # nonsense detection — discard
        return None
    data = _load_cache()
    data[path] = {"bpm": bpm, "mtime": os.path.getmtime(path)}
    _save_cache(data)
    return bpm


def cached_bpm(path):
    """Instant BPM from cache, or None. Never analyzes inline (transitions
    must not block); misses get filled by prewarm for next time."""
    entry = _load_cache().get(path)
    if not entry:
        return None
    try:
        if os.path.getmtime(path) != entry["mtime"]:
            return None  # file changed — stale
    except OSError:
        return None
    return entry["bpm"]


def prewarm(paths):
    """Background-analyze uncached local files (e.g. the queue head) so the
    BPM is hot before the transition."""
    if not available():
        return
    todo = [p for p in paths
            if os.path.isfile(p) and cached_bpm(p) is None]
    if not todo:
        return

    def run():
        for p in todo:
            analyze(p)

    threading.Thread(target=run, daemon=True).start()


def speed_for(out_bpm, in_bpm):
    """Playback speed for the incoming track to match the outgoing tempo.
    Pure function — unit-tested. None = don't beatmatch."""
    if not out_bpm or not in_bpm or out_bpm <= 0 or in_bpm <= 0:
        return None
    ratio = out_bpm / in_bpm
    # half/double-time feel reads as the same groove — prefer the closer ratio
    if ratio > 1.5:
        ratio /= 2
    elif ratio < 1 / 1.5:
        ratio *= 2
    if abs(ratio - 1) > CLAMP:
        return None
    return ratio
