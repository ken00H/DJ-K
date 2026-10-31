"""MPRIS D-Bus integration: makes DJ-K appear in GNOME/KDE media controls with
icon, track title and prev/play/next — exactly like Rhythmbox. Optional: uses
the system GObject introspection package (python3-gi, like mpv a system
install, not pip); silently off when absent (CI, Windows, headless)."""
import os

BUS_NAME = "org.mpris.MediaPlayer2.djk"
OBJECT_PATH = "/org/mpris/MediaPlayer2"

_NODE_XML = """
<node>
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/>
    <method name="Quit"/>
    <property name="CanQuit" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Next"/>
    <method name="Previous"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <method name="Play"/>
    <method name="Seek"><arg type="x" direction="in"/></method>
    <method name="SetPosition"><arg type="o" direction="in"/><arg type="x" direction="in"/></method>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="LoopStatus" type="s" access="readwrite"/>
    <property name="Rate" type="d" access="read"/>
    <property name="Shuffle" type="b" access="readwrite"/>
    <property name="Metadata" type="a{sv}" access="read"/>
    <property name="Volume" type="d" access="readwrite"/>
    <property name="Position" type="x" access="read"/>
    <property name="CanGoNext" type="b" access="read"/>
    <property name="CanGoPrevious" type="b" access="read"/>
    <property name="CanPlay" type="b" access="read"/>
    <property name="CanPause" type="b" access="read"/>
    <property name="CanSeek" type="b" access="read"/>
    <property name="CanControl" type="b" access="read"/>
  </interface>
</node>
"""

MICROSECONDS = 1_000_000


def playback_status(playing):
    """Pure mapping for tests: Player state → MPRIS PlaybackStatus string."""
    return "Playing" if playing else "Stopped"


def metadata_for(title):
    """Pure builder for tests: now-playing title → MPRIS metadata dict."""
    return {"xesam:title": (title or "DJ-K"), "xesam:artist": ["DJ-K"]}


def available():
    if os.name == "nt" or not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return False
    import importlib.util
    return importlib.util.find_spec("gi") is not None


def start(player):
    """Own the MPRIS bus name and mirror `player` state; no-op if unavailable."""
    if not available():
        return None
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    node = Gio.DBusNodeInfo.new_for_xml(_NODE_XML)
    for iface in node.interfaces:
        Gio.DBusNodeInfo.lookup_interface(node, iface.name)
    player_iface = node.interfaces[1].name
    state = {"status": "Stopped", "title": None, "pos": 0, "vol": 1.0}

    def props_for(name):
        if name == "PlaybackStatus":
            return GLib.Variant("s", state["status"])
        if name == "Metadata":
            m = metadata_for(state["title"])
            return GLib.Variant("a{sv}", {
                "xesam:title": GLib.Variant("s", m["xesam:title"]),
                "xesam:artist": GLib.Variant("as", m["xesam:artist"]),
            })
        if name == "Position":
            return GLib.Variant("x", int(state["pos"] * MICROSECONDS))
        if name == "Volume":
            return GLib.Variant("d", state["vol"])
        if name == "CanSeek":
            return GLib.Variant("b", True)
        if name in ("CanGoNext", "CanGoPrevious", "CanPlay",
                    "CanPause", "CanControl", "CanQuit"):
            return GLib.Variant("b", True)
        if name == "CanRaise":
            return GLib.Variant("b", False)
        if name == "HasTrackList":
            return GLib.Variant("b", False)
        if name == "Identity":
            return GLib.Variant("s", "DJ-K")
        if name == "DesktopEntry":
            return GLib.Variant("s", "djk")
        if name == "Rate":
            return GLib.Variant("d", 1.0)
        if name == "LoopStatus":
            return GLib.Variant("s", "None")
        if name == "Shuffle":
            return GLib.Variant("b", False)
        if name == "SupportedUriSchemes":
            return GLib.Variant("as", [])
        if name == "SupportedMimeTypes":
            return GLib.Variant("as", [])
        return None

    def emit_changed(changes):
        con = connection[0]
        if con is None:
            return
        # explicit nested builders — no pygobject coercion ambiguity
        vb = GLib.VariantBuilder(GLib.VariantType("(sa{sv}as)"))
        vb.add_value(GLib.Variant("s", player_iface))
        inner = GLib.VariantBuilder(GLib.VariantType("a{sv}"))
        for k in changes:
            v = props_for(k)
            if v is not None:
                entry = GLib.VariantBuilder(GLib.VariantType("{sv}"))
                entry.add_value(GLib.Variant("s", k))
                entry.add_value(GLib.Variant("v", v))  # wrap as variant type
                inner.add_value(entry.end())
        vb.add_value(inner.end())
        vb.add_value(GLib.Variant("as", []))
        con.emit_signal(None, OBJECT_PATH, "org.freedesktop.DBus.Properties",
                        "PropertiesChanged", vb.end())

    def poll_player():
        st = player.status()
        changes = []
        new_status = playback_status(st["playing"])
        if new_status != state["status"]:
            state["status"] = new_status
            changes.append("PlaybackStatus")
        if st["current"] != state["title"]:
            state["title"] = st["current"]
            changes.append("Metadata")
        if st["pos"] is not None:
            state["pos"] = st["pos"]
        if st["volume"] is not None:
            state["vol"] = st["volume"] / 100.0
        if changes:
            emit_changed(changes)
        return GLib.SOURCE_CONTINUE

    connection = [None]

    def on_bus_acquired(con, name):
        connection[0] = con

        def on_method(*a):
            # arity varies by pygobject: (…sender, path, iface, method, params, invocation[, user_data])
            invocation = a[-1]
            method, params, iface = a[-3], a[-2], a[-4]
            if iface == player_iface:
                if method == "Next":
                    player.skip()
                elif method in ("PlayPause", "Play"):
                    player.pause()
                elif method in ("Pause", "Stop"):
                    player.stop()
                elif method == "Previous":
                    player.seek(0)
                elif method == "Seek":
                    player.seek((state["pos"] or 0) + params[0] / MICROSECONDS)
                elif method == "SetPosition":
                    player.seek(params[1] / MICROSECONDS)
                invocation.return_value(None)
            elif method == "Quit":
                player.stop()
                invocation.return_value(None)

        def on_get(*a):
            prop = a[-1]  # (…, iface, prop) — leading args vary by pygobject
            return props_for(prop)

        def on_set(*a):
            prop, value = a[-2], a[-1]
            if prop == "Volume" and value is not None:
                player.volume(int(value * 100))
            return True

        # one registration per interface (root + Player) on the same path
        for iface in node.interfaces:
            con.register_object(OBJECT_PATH, iface, on_method, on_get, on_set)

    def on_name_lost(con, name):
        connection[0] = None  # another DJ-K instance owns it — stay silent

    Gio.bus_own_name(Gio.BusType.SESSION, BUS_NAME,
                     Gio.BusNameOwnerFlags.NONE,
                     on_bus_acquired, None, on_name_lost)
    GLib.timeout_add_seconds(1, poll_player)

    from . import glibloop
    glibloop.ensure_loop()
    return True
