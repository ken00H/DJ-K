"""Settings store: ~/.config/djjamal/settings.json with env-var precedence.

Resolution order per key: environment variable > settings file > default.
Live-toggleable keys are read through the helper functions (crossfade(), tts(),
...) so the UI can flip them without a restart; AI backend and path keys are
resolved once at import (restart to apply). The file may hold the OpenAI key,
so it is written with 0600 permissions."""
import json
import os
import threading
from pathlib import Path

FILE = Path.home() / ".config" / "djjamal" / "settings.json"
_lock = threading.Lock()

# key -> (env var, default, type, applies-live)
SCHEMA = {
    "crossfade":    ("DJ_CROSSFADE", "1", bool, True),
    "tts":          ("DJ_TTS", "1", bool, True),
    "beatmatch":    ("DJ_BEATMATCH", "1", bool, True),
    "musicgen":     ("DJ_MUSICGEN", "1", bool, True),
    "source_local": ("DJ_SOURCE_LOCAL", "1", bool, True),
    "source_youtube": ("DJ_SOURCE_YOUTUBE", "1", bool, True),
    "mpris":        ("DJ_MPRIS", "1", bool, False),
    "tray":         ("DJ_TRAY", "1", bool, False),
    "provider":     ("DJ_PROVIDER", "auto", str, True),  # llm.chat resolves it per call
    "llamacpp_url": ("DJ_LLAMACPP_URL", "http://127.0.0.1:8080", str, False),
    "llamacpp_model": ("DJ_LLAMACPP_MODEL", "local", str, False),
    "ollama_url":   ("OLLAMA_URL", "http://localhost:11434", str, False),
    "ollama_model": ("DJ_OLLAMA_MODEL", "gemma4:e2b-it-qat", str, False),
    "openai_model": ("DJ_OPENAI_MODEL", "gpt-4o-mini", str, False),
    "openai_api_key": ("OPENAI_API_KEY", "", str, True),  # llm.py resolves it per call
    "llm_timeout":  ("DJ_LLM_TIMEOUT", "300", int, False),
    "music_dir":    ("DJ_MUSIC_DIR", "~/Music", str, False),
    "tts_voice":    ("DJ_TTS_VOICE", "~/.config/djjamal/voices/en_US-lessac-medium.onnx", str, False),
    "gen_python":   ("DJ_GEN_PYTHON", "", str, False),
    "web_port":     ("DJ_WEB_PORT", "8090", int, False),
}
RESTART_KEYS = tuple(k for k, (_, _, _, live) in SCHEMA.items() if not live)


def _load_file():
    try:
        return json.loads(FILE.read_text())
    except (OSError, ValueError):
        return {}


def _coerce(raw, typ):
    if typ is bool:
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if typ is int:
        return int(raw)
    return str(raw)


def resolve(key):
    """Env var > settings file > default. Raises KeyError for unknown keys.
    A malformed env value falls through to file/default instead of crashing."""
    env, default, typ, _live = SCHEMA[key]
    if os.environ.get(env):
        try:
            return _coerce(os.environ[env], typ)
        except (TypeError, ValueError):
            pass
    stored = _load_file().get(key)
    if stored is not None:
        try:
            return _coerce(stored, typ)
        except (TypeError, ValueError):
            pass
    return _coerce(default, typ)


def snapshot():
    """All resolved settings as a dict (secrets included — mask at the edge)."""
    return {k: resolve(k) for k in SCHEMA}


def update(changes):
    """Validate + merge into the settings file (env vars always win over it).
    Returns the list of saved keys; unknown keys raise KeyError."""
    with _lock:
        data = _load_file()
        for k, v in changes.items():
            if k not in SCHEMA:
                raise KeyError(k)
            _, _, typ, _live = SCHEMA[k]
            data[k] = _coerce(v, typ)
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".json.tmp")
        try:
            os.unlink(tmp)  # a crashed run's leftover may carry wider perms
        except OSError:
            pass
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                     0o600)  # key-bearing from the first byte, not after chmod
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(data, indent=2))
        os.replace(tmp, FILE)  # atomic — no partially-written settings file
    return list(changes)


def mask(value):
    """Show enough of a secret to recognize it, never the whole thing."""
    if not value:
        return ""
    return value[:3] + "…" + value[-4:] if len(value) > 12 else "……"


# --- live-toggle helpers (read current state on every call) ---------------
def crossfade():
    return resolve("crossfade")


def tts():
    return resolve("tts")


def beatmatch():
    return resolve("beatmatch")


def musicgen():
    return resolve("musicgen")


def source_local():
    return resolve("source_local")


def source_youtube():
    return resolve("source_youtube")


def mpris():
    return resolve("mpris")


def tray():
    return resolve("tray")
