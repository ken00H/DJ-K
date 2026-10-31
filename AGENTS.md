# AGENTS.md — DJ-K

Personal AI DJ: natural-language chat that picks music, plays via mpv, talks like a radio DJ (on-air name: DJ-K), crossfades and beatmatches between tracks. Local library (`~/Music`) first, YouTube fallback via yt-dlp.

## Commands

- `./run.sh` — terminal REPL
- `./run.sh web` — web UI at http://127.0.0.1:8090 (`DJ_WEB_PORT` to change)
- No pip dependencies. Tests: `python3 -m unittest discover -s tests` (stdlib-only, network-free). Verify changes by running the REPL with a command like `/list`, or `curl http://127.0.0.1:8090/api/state` against the web UI.
- Requires: Linux or Windows, Python 3.10+, `mpv`, `yt-dlp` (2026+) on PATH, one AI backend (llama.cpp :8080, Ollama :11434, or `OPENAI_API_KEY`).

## Architecture rules

- **Stdlib only.** Do not add pip dependencies. Web server is `http.server` (no Flask/FastAPI), binds `127.0.0.1` only.
- **The brain never touches audio.** `djbrain.py` only returns JSON `{reply, action, tracks[]}`. Playback decisions stay there; audio execution stays in `player.py`/`mpvproc.py`.
- **`mpvproc.py` is the single place mpv launches.** Every source is validated (existing local file or `http(s)`/`ytsearch` URL) — keep that validation intact for any new source. This includes the TTS voice: `tts.py` synthesizes a wav and plays it via `mpvproc.launch`, never a second player. Queued YouTube queries are deferred `ytq:` markers; `player.py` resolves them at play time (URLs expire ~6h) — don't pre-resolve whole queues.
- **`llm.py` provider chain**: llama.cpp → Ollama → OpenAI, tried in order. Requests are pinned to loopback or `api.openai.com` — do not widen this.
- **Cross-platform (Linux + Windows).** mpv IPC: Unix sockets on POSIX, named pipes on Windows — all in `player.py` (`WINDOWS`, `_sock_ready`, `_new_sock_name`). Never add `AF_UNIX` usage outside `player.py`. Venv bin paths differ per OS (`musicgen._VENV_BIN`). CI runs ubuntu (3.10, 3.12) + windows (3.12); keep tests platform-neutral (no `/bin/*` fixtures without mocking).
- Entry points: `dj/main.py` (REPL) and `dj/web.py` (web); both share `enqueue_smart`, `generate_track`, `Player`, and `library`.
- **Optional heavy deps run as subprocesses, never imports**: piper (TTS CLI), MusicGen (venv python at `DJ_GEN_PYTHON`, called by `musicgen.py`), and librosa beat tracking (`beatmatch.py`, same venv). The main app must stay importable with none of them present — keep new integrations behind an `available()` check. Beatmatch is tempo-match only (no beat-phase alignment yet); `beatmatch.speed_for` is the pure ratio function.
- **Desktop integration (Linux) is optional system-gi, not pip**: `mpris.py`/`tray.py`/`glibloop.py` import the system `python3-gi` lazily behind `available()` and no-op on CI/Windows. pygobject closure arity varies — index callback args from the END (`a[-1]`), never by fixed positional names.

## Conventions

- Config: `DJ_*` env vars still work and ALWAYS override `~/.config/djjamal/settings.json` (the settings UI writes that file; schema + precedence live in `dj/settings.py` — add new keys to `SCHEMA` there, never read env directly in feature modules). Playback + music-source toggles must stay live-readable (`settings.crossfade()`, `settings.source_local()` etc.), AI/path/desktop keys are import-time. ALL feature gating goes through these helpers — never an ad-hoc env read in a feature module.
- Library cache: `~/.config/djjamal/library.json`, keyed to `DJ_MUSIC_DIR` (switching dirs triggers a rescan).
- Crossfade = two overlapping mpv processes with volume ramps (`player.py`).
- REPL slash commands: `/skip /pause /stop /queue /list /rescan /settings /quit` — anything else goes to the DJ brain. Web POST endpoints are CSRF-guarded (`web.cross_site`) — keep that check on any new POST route.

## Read before editing sensitive areas

- `README.md` — full architecture diagram, config table, roadmap.
- `CHANGELOG.md` — recent changes.
- `dj/project-ledger.md` — project status ledger (open loops, next steps).
