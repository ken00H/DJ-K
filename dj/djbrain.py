"""DJ brain: persona prompt + LLM call, returns {reply, action, tracks}."""
import json
import random
import re

from . import library, llm, settings

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
    src = (f"local library {'on' if settings.source_local() else 'OFF'}, "
           f"YouTube {'on' if settings.source_youtube() else 'OFF'}, "
           f"AI generation {'on' if settings.musicgen() else 'OFF'}")
    if settings.source_local():
        # shuffle before the cap: a fixed slice would bias the hint to the first
        # 120 tracks alphabetically and hide the rest of the library forever
        hint = list(tracks_hint or [])
        random.shuffle(hint)
        lib = "\n".join(f"- {t['name']}" for t in hint[:library.MAX_TRACKS_TO_LLM])
        user = (f"Sources available: {src}\nLocal library:\n{lib}\n\n"
                f"User says: {user_msg}\n\nReply with only the JSON object.")
    else:
        user = (f"Sources available: {src}\n\nUser says: {user_msg}"
                f"\n\nReply with only the JSON object.")
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
    d["reply"] = "" if d["reply"] is None else str(d["reply"])
    d["action"] = d.get("action", "chat") if d.get("action") in (
        "play", "queue", "playlist", "stop", "chat", "search", "generate") else "chat"
    tracks = d.get("tracks")
    if isinstance(tracks, str):  # LLM sent a bare string — one track, not chars
        tracks = [tracks]
    elif not isinstance(tracks, list):
        tracks = []
    d["tracks"] = [str(t) for t in tracks][:20]
    if d["action"] in ("play", "queue", "playlist", "search", "generate") and not d["tracks"]:
        d["action"] = "chat"  # playback action with nothing to play — don't hype a no-op
    return d
