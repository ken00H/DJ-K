"""Single place where mpv is launched + YouTube URL resolution. Fixed argv, shell=False."""
import subprocess
from urllib.parse import urlparse

from . import settings

ALLOWED_PREFIXES = ("http://", "https://", "ytsearch")


def validate_source(source):
    """A source must be an existing local file or a known URL scheme — nothing else
    is ever passed to mpv. Returns the source or raises ValueError."""
    import os
    if source.startswith("-"):
        raise ValueError(f"blocked suspicious source: {source!r}")
    if source.startswith(ALLOWED_PREFIXES):
        u = urlparse(source)
        if u.scheme in ("http", "https") and u.hostname:
            return source
        if u.scheme.startswith("ytsearch"):
            return source
        raise ValueError(f"blocked malformed URL: {source!r}")
    if os.path.isfile(source):  # local path (not starting with '-', no option injection)
        return source
    raise ValueError(f"blocked non-file non-URL source: {source!r}")


def launch(sock, start_volume, source, speed=1.0, loudnorm=None):
    argv = ["mpv", "--no-video", "--really-quiet", "--no-terminal",
            f"--input-ipc-server={sock}", f"--volume={int(start_volume)}"]
    if speed != 1.0:  # beatmatch: pitch-corrected tempo match (mpv default)
        argv.append(f"--speed={speed:.4f}")
    if settings.loudnorm() if loudnorm is None else loudnorm:
        # EBU R128 real-time loudness normalization — evens out track-to-track
        # volume jumps at transitions; lives on the filter layer so it never
        # touches the user's volume property (slider/duck stay authoritative)
        argv.append("--af=loudnorm")
    argv += ["--", validate_source(source)]
    try:
        return subprocess.Popen(argv, shell=False,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise ValueError("mpv not found on PATH — install mpv")


def resolve_youtube(query):
    """mpv 0.37's ytdl hook is flaky; resolve a direct bestaudio URL via the
    yt-dlp Python API (no shell involved). Returns (url, title)."""
    import yt_dlp
    opts = {"quiet": True, "format": "bestaudio", "noplaylist": True,
            "skip_download": True, "no_warnings": True,
            "socket_timeout": 15}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(f"ytsearch1:{query}", download=False)
        entry = info["entries"][0]
        url = entry.get("url") or ""
        if not url.startswith("https://"):
            raise ValueError(f"no audio URL for: {query!r}")
        return url, entry.get("title") or query
