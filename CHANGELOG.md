# Changelog

All notable changes to DJ Jamal are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [0.4.0] — 2026-10-31

### Added
- AI track generation: new `generate` action — "make me a lo-fi beat" synthesizes music with facebook/MusicGen-small in an isolated venv (`dj/musicgen.py`, subprocess, app stays stdlib-only); generated wav enqueues like any track; auto-disabled when the venv is absent (`DJ_MUSICGEN=0`, `DJ_GEN_PYTHON`); works in REPL and web UI
- 3 new tests (22 total)

## [0.3.0] — 2026-10-31

### Added
- DJ voice: optional piper TTS (`dj/tts.py`) — speaks DJ intros over music ducked to 25%, restores after; plays through the same validated mpv path; auto-disabled when piper or the voice model is absent (`DJ_TTS=0` to force off, `DJ_TTS_VOICE` to pick a voice)
- `Player.duck()` volume control via mpv IPC
- 4 TTS clip tests (19 total)

### Verified live
- Full playback pass on the real stack (llama.cpp Qwen3, 186 tracks, mpv): play, queue, both `/skip` paths, pause, stop, YouTube resolve + `ytq:` deferral, web `/api/state` — no code changes needed

## [0.2.1] — 2026-10-31

### Fixed
- `/skip` on the last track did nothing — now stops playback when the queue is empty
- Library cache served the old library for up to a day after switching `DJ_MUSIC_DIR` — cache is now keyed to the music dir (legacy caches rescan transparently)
- Race between `enqueue()` and the auto-advance loop could drop a queued track — popping is now guarded by the player lock
- "Now playing" reported tracks whose mpv had died instantly (bad/expired URL) — dead spawns now raise and are skipped
- Queued YouTube URLs expired (~6h) before playback — queries beyond the first now queue as `ytq:` markers and resolve at play time (first still resolves synchronously for a fast start); background resolve thread removed

## [0.2.0] — 2026-10-31

### Added
- Web UI (`dj/web.py` + `dj/index.html`): stdlib `http.server` (no new dependencies), dark page with chat box, now-playing bar, skip/pause/stop buttons; binds to `127.0.0.1` only, port via `DJ_WEB_PORT` (default 8090)
- `./run.sh web` launcher mode
- Fixed: `run.sh` crashed with `ModuleNotFoundError: dj` — `sys.path` bootstrap in `main.py` now runs before imports

## [0.1.0] — 2026-10-31

First working version.

### Added
- CLI REPL (`main.py`) with natural-language DJ chat and `/skip /pause /stop /queue /list /rescan /quit` commands
- DJ persona brain (`djbrain.py`): LLM returns `{reply, action, tracks[]}` JSON; picks tracks from local library, invents YouTube queries otherwise
- Provider chain (`llm.py`): llama.cpp (`:8080`, OpenAI-compatible) → Ollama → OpenAI, auto-fallback; explicit override via `DJ_PROVIDER`
- Local library scan (`library.py`): recursive audio scan of `~/Music`, 1-day JSON cache, fuzzy word-subset search
- Player (`player.py`): mpv JSON-IPC control, queue with auto-advance, pause, skip, stop
- Crossfade: dual-mpv volume-ramp overlap on track change (volume fade only — no beatmatching)
- YouTube playback (`mpvproc.py`): direct `bestaudio` URL resolution via yt-dlp Python API; mpv's built-in ytdl hook is broken on mpv 0.37, so resolution is bypassed
- Source validation: only existing local files or `http(s)`/`ytsearch` sources ever reach mpv; LLM requests pinned to loopback or `api.openai.com`
- `run.sh` launcher; `project-ledger.md` status ledger

### Fixed during build
- mpv 0.37 requires `--option=value` form (`--input-ipc-server value` exits fatally)
- `ytsearch1:` scheme was rejected by source validation
- System yt_dlp module (2024.04) cannot extract current YouTube — upgraded user-level install to 2026.10.26
- Ollama default model corrected to locally available `gemma4:e2b-it-qat`; CPU-bound models needed smaller library hints (120 tracks) and thinking disabled
