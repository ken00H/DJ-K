#!/usr/bin/env python3
"""DJ-K — personal AI DJ. Chat REPL that plays music via mpv."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import threading

from dj import djbrain, library, mpris, mpvproc, musicgen, settings, tray, tts
from dj.player import Player

BOLD, CYAN, MAGENTA, DIM, RESET = "\033[1m", "\033[36m", "\033[35m", "\033[2m", "\033[0m"


def generate_track(player, prompt, secs=None, notify=None):
    """Generate a track with MusicGen in a worker thread and queue it.
    notify(status_line) reports progress; the venv subprocess may take
    minutes on CPU."""
    if not musicgen.available():
        if notify:
            notify("musicgen unavailable — set up ~/.config/djjamal/gen-env (see README)")
        return

    def run():
        if notify:
            notify(f"cooking up: {prompt}")
        wav, err = musicgen.generate(prompt, secs) if secs else musicgen.generate(prompt)
        if not wav:
            if notify:
                notify(f"generation failed: {err}")
            return
        player.enqueue(wav, f"✨ AI: {prompt[:60]}")
        if notify:
            notify(f"fresh AI track queued: {prompt[:60]}")

    threading.Thread(target=run, daemon=True).start()


def enqueue_smart(player, lib, queries):
    """Local matches enqueue instantly; YouTube queries resolve at play time
    (first one synchronously so music starts fast, the rest as deferred
    'ytq:' markers — resolved URLs expire after ~6h, so pre-resolving a
    whole queue would leave dead links)."""
    pending_yt = []

    def resolve_later(qs):
        for q in qs:
            try:
                url, title = mpvproc.resolve_youtube(q)
                player.enqueue(url, title)
            except Exception as e:
                print(f"{DIM}yt resolve failed ({q}): {e}{RESET}")

    use_local = settings.source_local()
    use_yt = settings.source_youtube()
    for q in queries:
        hit = library.resolve(lib, q) if use_local else None
        if hit:
            player.enqueue(hit["path"], hit["name"])
        elif use_yt:
            pending_yt.append(q)
        else:
            print(f"{DIM}no music source enabled for: {q}{RESET}")
    if pending_yt:
        resolve_later(pending_yt[:1])     # first now, so playback starts quickly
        for q in pending_yt[1:]:
            player.enqueue(f"ytq:{q}", q)  # resolved when it reaches the deck


def dj_say(player, text):
    """Speak the DJ reply over ducked music in a background thread."""
    if not tts.available():
        return

    def run():
        proc = tts.speak(text)      # blocks during synthesis, plays after
        if not proc:
            return
        player.duck(True)
        try:
            proc.wait(timeout=90)
        except Exception:
            proc.terminate()
        player.duck(False)

    threading.Thread(target=run, daemon=True).start()


def main():
    if os.name == "nt":
        os.system("")  # enables ANSI escape processing in Windows terminals
    lib = library.scan()
    print(f"{MAGENTA}🎧 DJ-K{RESET} — {len(lib)} local tracks in {library.MUSIC_DIR}")
    print(f"{DIM}Commands: /skip /pause /stop /queue /list /settings /rescan /quit — or just talk.{RESET}")

    def on_start(title):
        print(f"{CYAN}♪ now playing: {title}{RESET}")

    player = Player(on_track_start=on_start)
    mpris.start(player)  # desktop presence: media controls (no-op if no gi)
    tray.start(player, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "assets", "djk.svg"))
    history = []

    while True:
        try:
            msg = input(f"{BOLD}you ▸ {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye. keep it spinning.")
            tts.stop_all()
            player.stop()
            break
        if not msg:
            continue

        if msg in ("/quit", "/exit", "q"):
            tts.stop_all()
            player.stop()
            break
        if msg == "/skip":
            player.skip()
            continue
        if msg == "/pause":
            player.pause()
            continue
        if msg == "/stop":
            player.stop()
            continue
        if msg == "/list":
            if not settings.source_local():
                print(f"{DIM}local source disabled in settings (/settings or the gear button){RESET}")
                continue
            names = [t["name"] for t in (library.search(lib, "") or lib)]
            for n in names[:30]:
                print(f"  {n}")
            if len(names) > 30:
                print(f"{DIM}  … and {len(names) - 30} more — use the web UI library browser{RESET}")
            continue
        if msg == "/rescan":
            lib = library.scan(force=True)
            print(f"rescanned: {len(lib)} tracks")
            continue
        if msg == "/settings":
            for k, v in settings.snapshot().items():
                shown = settings.mask(v) if k == "openai_api_key" else v
                print(f"  {k}: {shown}")
            continue
        if msg == "/queue":
            for s, t in player.queue:
                print(f"  {t}")
            print(f"  {DIM}({len(player.queue)} queued){RESET}")
            continue

        try:
            brain = djbrain.think(msg, tracks_hint=lib, history=history)
        except RuntimeError as e:
            print(f"{DIM}{e}{RESET}")
            print("Local commands still work: /list /play <name> …")
            continue
        except Exception as e:
            print(f"{DIM}brain hiccup: {e}{RESET}")
            continue
        except KeyboardInterrupt:  # Ctrl+C during a blocking LLM call
            print("\nbye. keep it spinning.")
            tts.stop_all()
            player.stop()
            break

        history.append({"role": "user", "content": msg})
        history.append({"role": "assistant", "content": brain["reply"]})
        del history[:-6]  # same window djbrain.think uses
        print(f"{MAGENTA}DJ ▸{RESET} {brain['reply']}")

        action, tracks = brain["action"], brain["tracks"]
        try:
            if action == "stop":
                player.stop()
            elif action == "generate" and tracks:
                generate_track(player, tracks[0],
                               notify=lambda s: print(f"{DIM}{s}{RESET}"))
                dj_say(player, brain["reply"])
            elif action in ("play", "search") and tracks:
                player.stop()
                enqueue_smart(player, lib, tracks)
                dj_say(player, brain["reply"])
            elif action in ("queue", "playlist") and tracks:
                enqueue_smart(player, lib, tracks)
                print(f"{DIM}queued {len(tracks)} tracks{RESET}")
                dj_say(player, brain["reply"])
        except ValueError as e:
            print(f"{DIM}skipped a bad source: {e}{RESET}")
        except KeyboardInterrupt:  # Ctrl+C during playback actions
            print("\nbye. keep it spinning.")
            tts.stop_all()
            player.stop()
            break


if __name__ == "__main__":
    main()
