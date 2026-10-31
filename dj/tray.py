"""System tray icon for DJ-K (taskbar presence). Optional: needs system
python3-gi with AppIndicator3 (Ubuntu GNOME ships the shell side via
ubuntu-appindicators). Silent no-op when unavailable."""
import os

from . import glibloop, mpris  # same availability base: gi + session bus


def _indicator_module():
    """Return the AppIndicator module — classic or Ayatana fork (same API)."""
    import gi
    for name in ("AppIndicator3", "AyatanaAppIndicator3"):
        try:
            gi.require_version(name, "0.1")
            return getattr(__import__(
                "gi.repository", fromlist=[name]), name)
        except (ValueError, ImportError):
            continue
    return None


def available():
    return mpris.available() and _indicator_module() is not None


def start(player, icon_path):
    """Show a tray icon with play controls; no-op if unsupported."""
    AppIndicator3 = _indicator_module()
    if AppIndicator3 is None:
        return None
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    menu = Gtk.Menu()

    now = Gtk.MenuItem(label="♪ DJ-K")
    now.set_sensitive(False)
    menu.append(now)
    menu.append(Gtk.SeparatorMenuItem())

    def item(label, fn):
        mi = Gtk.MenuItem(label=label)
        mi.connect("activate", lambda *_: fn())
        menu.append(mi)

    item("⏭ Skip", player.skip)
    item("⏸ Play/Pause", player.pause)
    item("⏹ Stop", player.stop)
    menu.append(Gtk.SeparatorMenuItem())
    item("✕ Quit DJ-K", lambda: (player.stop(), os._exit(0)))
    menu.show_all()

    ind = AppIndicator3.Indicator.new(
        "djk", icon_path, AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
    ind.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
    ind.set_menu(menu)
    glibloop.ensure_loop()
    return ind
