# 🎧 DJ Jamal

A personal AI DJ for the terminal. Talk to it in plain language — it picks the music, plays it, talks like a radio DJ, and crossfades between tracks.

```
you ▸ gimme a metal playlist for the gym
DJ ▸ Jamal in the booth, we're turning this gym into a metal blast chamber! ...
♪ now playing: Avenged Sevenfold - Nightmare
```

## Features

- **Natural language control** — "play something chill", "queue Rammstein", "stop the music"
- **Local library first** — scans `~/Music`, matches your files before falling back to YouTube
- **YouTube fallback** — anything not local resolves and streams via yt-dlp
- **DJ persona** — LLM-powered radio-host banter between tracks
- **Crossfade** — volume-ramp blend on every track change (set `DJ_CROSSFADE=0` to disable)
- **Pluggable AI** — llama.cpp → Ollama → OpenAI, tried in that order automatically

## Requirements

- Linux, Python 3.10+ (stdlib only, no pip dependencies)
- `mpv` (playback)
- `yt-dlp` **2026+** in `~/.local/bin` or on PATH (YouTube resolution):
  `pip install --user --break-system-packages --upgrade yt-dlp`
- An AI backend — any one of:
  - **llama.cpp** `llama-server` on `http://127.0.0.1:8080` (default first choice)
  - **Ollama** on `localhost:11434` with a pulled model
  - **OpenAI** — `export OPENAI_API_KEY=...`

## Run

```bash
./run.sh          # terminal REPL
./run.sh web      # web UI → http://127.0.0.1:8090
```

Web UI: dark page with chat box, now-playing bar, skip/pause/stop buttons.
Stdlib-only server (no FastAPI/Flask); binds to `127.0.0.1` only.
Port configurable via `DJ_WEB_PORT`.

Then just talk. Commands:

| Command | Action |
|---|---|
| `/skip` | next track (crossfades) |
| `/pause` | pause / resume |
| `/stop` | stop playback, clear queue |
| `/queue` | show queue |
| `/list` | list local library |
| `/rescan` | rescan music folder |
| `/quit` | exit |

Anything else goes to the DJ brain.

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `DJ_MUSIC_DIR` | `~/Music` | music folder to scan |
| `DJ_PROVIDER` | `auto` | force `llamacpp` / `ollama` / `openai` |
| `DJ_LLAMACPP_URL` | `http://127.0.0.1:8080` | llama.cpp server |
| `DJ_OLLAMA_MODEL` | `gemma4:e2b-it-qat` | Ollama model |
| `DJ_OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model |
| `DJ_LLM_TIMEOUT` | `300` | LLM request timeout (seconds) |
| `DJ_CROSSFADE` | `1` | `0` disables crossfade |

Library cache lives at `~/.config/djjamal/library.json` (keyed to `DJ_MUSIC_DIR`, refreshed daily, or `/rescan`).

## How it works

```
you ─► main.py (REPL) ─► djbrain.py ─► llm.py (llama.cpp → Ollama → OpenAI)
                              │  JSON: {reply, action, tracks[]}
                              ▼
                        library.py — local match? ─► yes ─► player.py ─► mpv
                                                 └► no ─► mpvproc.resolve_youtube() (yt-dlp)
```

- The brain **never touches audio** — it only returns an action + track list
- `mpvproc.py` is the single place mpv launches; every source is validated
  (existing local file or `http(s)`/`ytsearch` URL only)
- YouTube queries resolve just before playback (direct URLs expire ~6h):
  the first query resolves immediately so music starts fast, the rest queue
  as deferred queries and resolve when they reach the deck
- LLM requests are pinned to loopback or `api.openai.com` — nothing else
- Crossfade overlaps two mpv processes with volume ramps (no beatmatching yet)

## Files

| File | Role |
|---|---|
| `main.py` | CLI REPL, command handling |
| `web.py` + `index.html` | web UI (stdlib http.server + one page) |
| `djbrain.py` | DJ persona prompt, JSON action parsing |
| `llm.py` | provider chain: llama.cpp / Ollama / OpenAI |
| `library.py` | scan + cache + fuzzy search of music folder |
| `player.py` | queue, mpv IPC control, crossfade |
| `mpvproc.py` | mpv launch (validated sources) + YouTube URL resolution |
| `project-ledger.md` | project status ledger |

## Roadmap ideas

- True beatmatching (tempo analysis)
- AI music generation hook (e.g. MusicGen)
- Voice output (TTS DJ intros)
