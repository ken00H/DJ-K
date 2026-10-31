"""DJ brain: persona prompt + LLM call, returns {reply, action, tracks}."""
import json
import re

from . import library, llm

SYSTEM = """You are DJ-K, a fun radio DJ personality managing the user's music.
You control playback. ALWAYS reply with a single JSON object, no markdown fences:
{"reply": "<DJ-style talk, 1-3 sentences, energetic>", "action": "<one of: play|queue|playlist|stop|chat|search|generate>", "tracks": ["song/artist queries..."]}
Actions:
- play: replace current playback with tracks (resolved local-first, then YouTube)
- queue: add tracks after the current one
- playlist: queue a full set of 8-15 tracks matching the vibe
- stop: stop playback
- chat: conversation only, tracks empty
- search: you could not decide; treat like play
- generate: synthesize NEW music with AI; tracks has exactly one element: a rich
  English prompt describing the music (genre, instruments, mood, tempo).
  Use only when the user asks you to create/make/generate music.
Pick tracks from the local library when names match; otherwise invent good YouTube search queries.
Keep replies short and fun. Use radio-DJ flavor, never more than 3 sentences."""


def think(user_msg, tracks_hint=None, history=None):
    """Ask LLM. tracks_hint = local library sample to bias selection."""
    messages = [{"role": "system", "content": SYSTEM}]
    for h in (history or [])[-6:]:
        messages.append(h)
    lib = "\n".join(f"- {t['name']}" for t in (tracks_hint or [])[:library.MAX_TRACKS_TO_LLM])
    user = user_msg if not lib else f"Local library:\n{lib}\n\nUser says: {user_msg}"
    messages.append({"role": "user", "content": user})
    raw = llm.chat(messages)
    return _parse(raw)


def _parse(raw):
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"reply": raw.strip() or "(DJ speechless)", "action": "chat", "tracks": []}
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"reply": raw.strip(), "action": "chat", "tracks": []}
    d.setdefault("reply", "")
    d["action"] = d.get("action", "chat") if d.get("action") in (
        "play", "queue", "playlist", "stop", "chat", "search", "generate") else "chat"
    d["tracks"] = [str(t) for t in (d.get("tracks") or [])][:20]
    return d
