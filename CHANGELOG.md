# Changelog

All notable changes to DJ Jamal are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [0.9.1] — 2026-11-01

### Added
- Per-source toggles: **Local library** and **YouTube** can be turned off independently (live, instant) — `DJ_SOURCE_LOCAL` / `DJ_SOURCE_YOUTUBE` env equivalents; when both are off for a query, DJ-K says so instead of silently failing
- Desktop toggles: **Media controls (MPRIS)** and **Tray icon** on/off (restart-apply) — `DJ_MPRIS` / `DJ_TRAY`
- Settings modal reorganized into Music sources / Playback / Desktop / AI backend / Advanced, with a pinned Save bar; the library panel hides when the local source is off
- The DJ brain now receives the live source list ("Sources available: local library on, YouTube OFF, …") and steers accordingly
- 4 new tests (45 total)

### Verified live
- Local off: `/api/track` → 400, library panel hidden, and a Sabaton request resolved through YouTube (mpv streaming from googlevideo.com proves the reroute)

## [0.9.0] — 2026-11-01

### Added
- Settings: `dj/settings.py` store at `~/.config/djjamal/settings.json` (0600) with env-var-over-file precedence; web settings UI (gear button → modal): playback toggles (crossfade/DJ voice/beatmatch/music-gen) apply live, AI backend (provider, llama.cpp/Ollama URLs + models, OpenAI key with masking, timeout) and paths (music folder, TTS voice) restart-apply with a clear "restart needed" hint; `GET/POST /api/settings` (key masked; masked key posted back is a no-op); REPL `/settings`
- Logo: `assets/djk-logo.svg` (emblem + DJ-K wordmark, purple→cyan) in the README header; emblem inline in the web header; SVG favicon (browser tab/taskbar identity)
- 7 settings tests (38 total)

### Changed
- `player`/`tts`/`beatmatch`/`musicgen`/`llm`/`library` read config through `settings` instead of import-time env constants (env vars unchanged in effect)

## [0.8.0] — 2026-11-01

### Changed
- Rebrand: the product and on-air persona are now **DJ-K** everywhere user-visible (README, REPL banner, web UI, brain persona, launchers). Internal identifiers (`dj/` package, `DJ_*` env vars, `~/.config/djjamal/`) unchanged by design.

### Added
- Desktop presence (Linux): MPRIS registration (`org.mpris.MediaPlayer2.djk`) — media controls show track title and prev/play/next that control playback for real; tray icon via AppIndicator/Ayatana with Skip/Play-Pause/Stop/Quit; `run.sh desktop` and `run.sh install-desktop` modes (icon + app-grid entry)
- New modules: `dj/mpris.py`, `dj/tray.py`, `dj/glibloop.py` (shared GLib loop thread); all optional, zero pip installs (system `python3-gi`), silent no-ops where unsupported
- `assets/djk.svg` app icon; 2 new tests (31 total)

### Verified live
- MPRIS `PlaybackStatus=Playing`, `Metadata` title matches the playing track; a D-Bus `Next` call advanced the real queue (crossfade) — checked next to Rhythmbox's own registration

## [0.7.2] — 2026-11-01

### Added
- Web chat history persists across page reloads (`/api/history` + render on load)
- README: badge header, live web-UI screenshot (`assets/webui.png`), LICENSE section; MIT `LICENSE` file added

## [0.7.1] — 2026-11-01

### Fixed (hardening sweep — closes the original audit's improvement list)
- `llm._assert_safe`: `::1` URLs no longer crash on `gethostbyname` (literal loopback IPs skip resolution)
- Web API: malformed JSON now returns 400 instead of an unhandled exception; DNS-rebinding guard — requests with a non-loopback `Host` header get 403
- REPL `/list` caps at 30 lines with a pointer to the web library browser

## [0.7.0] — 2026-11-01

### Added
- Web UI upgrade: live queue panel, searchable library browser (click to queue, ▶ to play), volume slider, seek bar with time display, BPM badge on the now-playing bar; library panel hidden on narrow screens
- Player: `volume()` get/set, `seek()`, `status()` (volume/pos/duration/bpm); `_ipc_query()` reads mpv IPC responses (both POSIX sockets and Windows named pipes)
- API: `/api/library` (track list), `/api/track` (play/queue by path — library-membership-checked), `volume`/`seek` commands on `/api/cmd`

### Verified live
- Play-by-path, volume set (100→42 reported back), seek (pos jumped to 31.8s), BPM badge (143.6), out-of-library path rejected with 400

## [0.6.0] — 2026-11-01

### Added
- Beatmatch: tempo-matched transitions — librosa BPM detection (first 60s per track, cached in `~/.config/djjamal/bpm.json`), incoming local track launches at a pitch-preserved `--speed` matching the outgoing tempo (±10% clamp, half/double-time aware); queue head pre-warmed in background; YouTube sources fall back to plain crossfade; `DJ_BEATMATCH=0` disables; shares the generation venv (`pip install librosa`)
- 5 new tests (27 total)

### Verified live
- 8 tracks analyzed (86–172 BPM, all plausible); transition Bullet For My Valentine (161.5 BPM) into Five Finger Death Punch (152.0 BPM) launched mpv with exactly `--speed=1.0625`

## [0.5.0] — 2026-10-31

### Added
- Windows support: mpv IPC via named pipes (`\\.\pipe\`) instead of Unix sockets, ANSI colors enabled in Windows terminals, per-OS generation-venv path, `run.bat` launcher; CI now runs the test suite on `windows-latest` too
- README: Windows requirements and platform notes

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
