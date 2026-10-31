#!/usr/bin/env python3
"""DJ Jamal — AI personal DJ. Chat REPL that plays music via mpv."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dj import djbrain, library, mpvproc
from dj.player import Player

BOLD, CYAN, MAGENTA, DIM, RESET = "\033[1m", "\033[36m", "\033[35m", "\033[2m", "\033[0m"


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

    for q in queries:
        hit = library.resolve(lib, q)
        if hit:
            player.enqueue(hit["path"], hit["name"])
        else:
            pending_yt.append(q)
    if pending_yt:
        resolve_later(pending_yt[:1])     # first now, so playback starts quickly
        for q in pending_yt[1:]:
            player.enqueue(f"ytq:{q}", q)  # resolved when it reaches the deck


def main():
    lib = library.scan()
    print(f"{MAGENTA}🎧 DJ Jamal{RESET} — {len(lib)} local tracks in {library.MUSIC_DIR}")
    print(f"{DIM}Commands: /skip /pause /stop /queue /list /rescan /quit — or just talk.{RESET}")

    def on_start(title):
        print(f"{CYAN}♪ now playing: {title}{RESET}")

    player = Player(on_track_start=on_start)
    history = []

    while True:
        try:
            msg = input(f"{BOLD}you ▸ {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye. keep it spinning.")
            player.stop()
            break
        if not msg:
            continue

        if msg in ("/quit", "/exit", "q"):
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
            for t in library.search(lib, "") or lib:
                print(f"  {t['name']}")
            continue
        if msg == "/rescan":
            lib = library.scan(force=True)
            print(f"rescanned: {len(lib)} tracks")
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

        history.append({"role": "user", "content": msg})
        history.append({"role": "assistant", "content": brain["reply"]})
        print(f"{MAGENTA}DJ ▸{RESET} {brain['reply']}")

        action, tracks = brain["action"], brain["tracks"]
        try:
            if action == "stop":
                player.stop()
            elif action in ("play", "search") and tracks:
                player.stop()
                enqueue_smart(player, lib, tracks)
            elif action in ("queue", "playlist") and tracks:
                enqueue_smart(player, lib, tracks)
                print(f"{DIM}queued {len(tracks)} tracks{RESET}")
        except ValueError as e:
            print(f"{DIM}skipped a bad source: {e}{RESET}")


if __name__ == "__main__":
    main()
