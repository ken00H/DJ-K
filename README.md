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
- **DJ voice** — optional piper TTS speaks intros over ducked music (`DJ_TTS=0` to disable)
- **AI track generation** — optional MusicGen hook: "make me a chill lo-fi beat" synthesizes a fresh track locally
- **Crossfade** — volume-ramp blend on every track change (set `DJ_CROSSFADE=0` to disable)
- **Beatmatch** — optional tempo-matched transitions: librosa detects BPM, incoming track speed-matches the outgoing one (±10%, pitch-preserved; `DJ_BEATMATCH=0` to disable)
- **Pluggable AI** — llama.cpp → Ollama → OpenAI, tried in that order automatically

## Requirements

- Linux **or Windows 10+**, Python 3.10+ (stdlib only, no pip dependencies)
- `mpv` (playback) — on Windows, put `mpv.exe` on PATH (e.g. via `winget install mpv`)
- `yt-dlp` **2026+** in `~/.local/bin` or on PATH (YouTube resolution):
  `pip install --user --break-system-packages --upgrade yt-dlp` (Linux) or
  `pip install --user --upgrade yt-dlp` (Windows)
- An AI backend — any one of:
  - **llama.cpp** `llama-server` on `http://127.0.0.1:8080` (default first choice)
  - **Ollama** on `localhost:11434` with a pulled model
  - **OpenAI** — `export OPENAI_API_KEY=...`

## Run

```bash
./run.sh          # terminal REPL (Linux/macOS)
./run.sh web      # web UI → http://127.0.0.1:8090
run.bat           # terminal REPL (Windows)
run.bat web       # web UI (Windows)
```

Web UI: dark page with chat box, now-playing bar (title, BPM badge, seek bar),
skip/pause/stop buttons, volume slider, live queue panel, and a searchable
library browser (click a track to queue it, ▶ to play it now).
Stdlib-only server (no FastAPI/Flask); binds to `127.0.0.1` only.
Port configurable via `DJ_WEB_PORT`.

Platform notes: mpv control uses Unix domain sockets on POSIX and named pipes
(`\\.\pipe\`) on Windows — handled in `player.py`. Config/cache live under
`~/.config/djjamal/` on both platforms. TTS and music generation are optional
and follow the same env vars on Windows (piper needs a Windows build; the
generation venv uses `Scripts\python.exe` automatically).

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
| `DJ_TTS` | `1` | `0` disables the DJ voice |
| `DJ_TTS_VOICE` | `~/.config/djjamal/voices/en_US-lessac-medium.onnx` | piper voice model |
| `DJ_MUSICGEN` | `1` | `0` disables AI generation |
| `DJ_BEATMATCH` | `1` | `0` disables tempo-matched transitions |
| `DJ_GEN_PYTHON` | `~/.config/djjamal/gen-env/bin/python` | python of the generation venv |

**DJ voice (optional):** `pip install --user --break-system-packages piper-tts`, then
download a voice, e.g.
`curl -L -o ~/.config/djjamal/voices/en_US-lessac-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx`
(+ the `.onnx.json` next to it). Without piper, the app silently skips TTS.

**AI track generation (optional):** runs facebook/MusicGen-small in an isolated
venv (the app itself stays stdlib-only; generation is a subprocess):
```bash
python3 -m venv ~/.config/djjamal/gen-env
~/.config/djjamal/gen-env/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
~/.config/djjamal/gen-env/bin/pip install "transformers<5" scipy
```
Then just ask the DJ: "generate a chill lo-fi beat". First use downloads the
model (~2.4 GB to `~/.cache/huggingface`). CPU synthesis takes minutes per
clip — the DJ queues it in the background and tells you when it lands.
Without the venv, generation is silently unavailable.

**Beatmatch (optional):** shares the generation venv — one extra package:
```bash
~/.config/djjamal/gen-env/bin/pip install librosa
```
BPM is detected per track (first 60s, cached at `~/.config/djjamal/bpm.json`),
and on transitions between local tracks the incoming one plays at a
pitch-preserved speed matching the outgoing tempo (±10% clamp, half/double-time
aware). YouTube-to-anything transitions use the plain crossfade.

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

- Beat-phase alignment (start transitions exactly on the beat — needs beat-grid data, not just BPM)
- Voice input (speech-to-text DJ requests)
