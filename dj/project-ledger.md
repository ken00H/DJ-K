# Project Ledger

## Open (actively working)
| Project | Next step | Last touched |
|---------|-----------|--------------|
| DJ Jamal (AI personal DJ) | idle — roadmap + hardening complete (v0.7.1); candidates: beat-phase, voice input (README roadmap) | 2026-11-01 |

## Parked (interesting, paused ON PURPOSE)
| Project | Reopen trigger | Closed? |
|---------|----------------|---------|

## Closed (done or deliberately abandoned)
| Project | Outcome | Date |
|---------|---------|------|

## Done-list (wins, one line each)
- DJ Jamal v0.1 shipped: CLI AI DJ — local 186-track library + YouTube, crossfade, llama.cpp/Ollama/OpenAI auto-fallback
- DJ Jamal v0.2 shipped: web UI (stdlib server + dark page), run.sh web mode
- DJ Jamal v0.2.1: full audit — fixed skip-on-last-track, stale cache on dir switch, enqueue race, dead-mpv now-playing lie, YouTube URL expiry (deferred `ytq:` resolve)
- DJ Jamal v0.3.0: full playback verified live on real stack; DJ voice (piper TTS over ducked music) shipped
- DJ Jamal v0.4.0: AI track generation (MusicGen-small, isolated venv, ~7 min/clip on CPU)
- DJ Jamal v0.5.0: Windows support — named-pipe mpv IPC, run.bat, windows-latest CI green; real-desktop Windows run still pending
- DJ Jamal v0.6.0: beatmatch shipped — librosa BPM (cached), pitch-preserved speed match ±10%, verified live at --speed=1.0625; ORIGINAL ROADMAP COMPLETE
- DJ Jamal v0.7.0: web UI is a real player — queue panel, library browser, volume, seek, BPM badge
- DJ Jamal v0.7.1: hardening sweep — ::1 crash, JSON 400, Host-header guard, /list cap; AUDIT LEDGER CLEAN
