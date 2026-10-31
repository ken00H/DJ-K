"""Shared GLib main loop thread (default main context), idempotently started.
Used by both mpris.py and tray.py so integration modules don't each spawn a
competing loop on the same context."""
import threading

_started = threading.Lock()
_running = False


def ensure_loop():
    """Start ONE GLib MainLoop thread on the default context; no-op after."""
    global _running
    with _started:
        if _running:
            return
        from gi.repository import GLib
        threading.Thread(target=GLib.MainLoop().run,
                         daemon=True, name="djk-glib").start()
        _running = True
