"""Local music library: scan folder, cache track list, fuzzy search."""
import json
import os
import time
from pathlib import Path

from . import settings

MUSIC_DIR = Path(os.path.expanduser(settings.resolve("music_dir")))
CACHE = Path.home() / ".config" / "djjamal" / "library.json"
AUDIO_EXT = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav", ".wma", ".aac"}

MAX_TRACKS_TO_LLM = 120  # ponytail: cap context for CPU-speed LLMs; paginate/summarize if needed


def scan(force=False):
    """Return list of track dicts {path, name}. Cached, 1 day TTL.
    Cache is keyed to MUSIC_DIR so switching dirs never serves the old list."""
    if CACHE.exists() and not force and time.time() - CACHE.stat().st_mtime < 86400:
        cached = json.loads(CACHE.read_text())
        # legacy caches were a bare list; current caches carry their dir
        if isinstance(cached, dict) and cached.get("dir") == str(MUSIC_DIR):
            return cached["tracks"]
    tracks = []
    for p in sorted(MUSIC_DIR.rglob("*")):
        if p.suffix.lower() in AUDIO_EXT:
            tracks.append({"path": str(p), "name": p.stem})
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"dir": str(MUSIC_DIR), "tracks": tracks}))
    return tracks


def search(tracks, query):
    """Fuzzy-ish search: all words in query appear in track name (case-insensitive)."""
    words = query.lower().split()
    return [t for t in tracks if all(w in t["name"].lower() for w in words)]


def resolve(tracks, query):
    """Best single match for a query, or None."""
    hits = search(tracks, query)
    if not hits:
        return None
    # prefer shortest name (tightest match)
    return min(hits, key=lambda t: len(t["name"]))
