"""Smoke tests: pure logic only — no mpv, no audio, no network, no LLM."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dj import djbrain, library, mpvproc, tts


class ValidateSource(unittest.TestCase):
    def test_local_file_ok(self):
        with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
            self.assertEqual(mpvproc.validate_source(f.name), f.name)

    def test_https_ok(self):
        self.assertEqual(mpvproc.validate_source("https://example.com/a.mp3"),
                         "https://example.com/a.mp3")

    def test_ytsearch_ok(self):
        self.assertEqual(mpvproc.validate_source("ytsearch1:metal"),
                         "ytsearch1:metal")

    def test_option_injection_blocked(self):
        self.assertRaises(ValueError, mpvproc.validate_source, "--volume=0")

    def test_missing_file_blocked(self):
        self.assertRaises(ValueError, mpvproc.validate_source, "/no/such/file.mp3")

    def test_ftp_blocked(self):
        self.assertRaises(ValueError, mpvproc.validate_source,
                          "ftp://example.com/a.mp3")


class BrainParse(unittest.TestCase):
    def test_plain_json(self):
        d = djbrain._parse('{"reply": "hi", "action": "play", "tracks": ["a"]}')
        self.assertEqual((d["reply"], d["action"], d["tracks"]), ("hi", "play", ["a"]))

    def test_json_with_surrounding_text(self):
        d = djbrain._parse('Sure! {"reply": "hi", "action": "queue", "tracks": ["a"]}')
        self.assertEqual(d["action"], "queue")

    def test_bad_action_becomes_chat(self):
        d = djbrain._parse('{"reply": "hi", "action": "delete-everything"}')
        self.assertEqual(d["action"], "chat")

    def test_garbage_becomes_chat(self):
        d = djbrain._parse("just talking, no json")
        self.assertEqual(d["action"], "chat")
        self.assertEqual(d["tracks"], [])

    def test_non_string_tracks_coerced(self):
        d = djbrain._parse('{"reply": "hi", "action": "play", "tracks": [1, "a"]}')
        self.assertEqual(d["tracks"], ["1", "a"])

    def test_generate_action_accepted(self):
        d = djbrain._parse('{"reply": "on it", "action": "generate", "tracks": ["lo-fi beat"]}')
        self.assertEqual(d["action"], "generate")
        self.assertEqual(d["tracks"], ["lo-fi beat"])

    def test_string_tracks_wrapped_not_split_chars(self):
        d = djbrain._parse('{"reply": "hi", "action": "play", "tracks": "one song"}')
        self.assertEqual(d["tracks"], ["one song"])

    def test_dict_tracks_dropped(self):
        d = djbrain._parse('{"reply": "hi", "action": "play", "tracks": {"a": 1}}')
        self.assertEqual(d["tracks"], [])


class MusicGen(unittest.TestCase):
    def test_available_false_without_venv(self):
        from dj import musicgen
        with mock.patch.object(musicgen, "VENV_PY", Path("/no/such/python")):
            self.assertFalse(musicgen.available())

    def test_generate_prompt_sanitized_and_secs_clamped(self):
        # generate() must sanitize before touching the subprocess; probe via a fake runner
        from dj import musicgen
        seen = {}

        def fake_run(argv, **kw):
            seen["prompt"] = argv[4]
            seen["secs"] = argv[5]
            raise subprocess.CalledProcessError(1, "py")  # fail fast

        with mock.patch.object(musicgen, "VENV_PY", Path("/bin/true")), \
             mock.patch.object(musicgen, "available", lambda: True), \
             mock.patch.object(musicgen.subprocess, "run", fake_run):
            musicgen.generate("  lo-fi\n  beat  ", secs=999)
        self.assertEqual(seen["prompt"], "lo-fi beat")
        self.assertEqual(seen["secs"], "30")


class Library(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "a.mp3").touch()
        (self.tmp / "sub").mkdir()
        (self.tmp / "sub" / "b.flac").touch()
        (self.tmp / "notes.txt").touch()
        patcher = mock.patch.object(library, "MUSIC_DIR", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)
        cache = self.tmp / "library.json"
        patcher = mock.patch.object(library, "CACHE", cache)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_scan_finds_audio_only(self):
        names = [t["name"] for t in library.scan()]
        self.assertEqual(names, ["a", "b"])

    def test_cache_roundtrip(self):
        first = library.scan()
        self.assertEqual(library.scan(), first)  # served from cache

    def test_cache_keyed_to_music_dir(self):
        library.scan()
        library.CACHE.write_text(json.dumps(
            {"dir": "/some/other/dir", "tracks": [{"path": "x", "name": "stale"}]}))
        names = [t["name"] for t in library.scan()]
        self.assertEqual(names, ["a", "b"])  # dir mismatch -> rescan, not stale

    def test_corrupt_cache_recovered_not_crash(self):
        library.CACHE.write_text("{not json")
        names = [t["name"] for t in library.scan()]
        self.assertEqual(names, ["a", "b"])

    def test_scan_atomic_write_leaves_no_tmp(self):
        library.scan()
        leftovers = [p for p in self.tmp.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_search_and_resolve(self):
        tracks = library.scan()
        self.assertEqual(library.search(tracks, "b")[0]["name"], "b")
        self.assertEqual(library.resolve(tracks, "a")["name"], "a")
        self.assertIsNone(library.resolve(tracks, "nothing matches this"))


class TTS(unittest.TestCase):
    def test_short_text_untouched(self):
        self.assertEqual(tts.clip("Jam in the house!"), "Jam in the house!")

    def test_whitespace_collapsed(self):
        self.assertEqual(tts.clip("  Jam   in \n the  house  "), "Jam in the house")

    def test_long_text_capped_and_ends_clean(self):
        out = tts.clip("word " * 200)
        self.assertLessEqual(len(out), tts.MAX_CHARS + 1)
        self.assertTrue(out.endswith((".", "!", "?", "…")), out[-5:])

    def test_clip_prefers_sentence_boundary(self):
        text = ("First sentence here. " * 30).strip()
        out = tts.clip(text)
        self.assertTrue(out.endswith("."), out[-5:])


class Beatmatch(unittest.TestCase):
    def setUp(self):
        from dj import beatmatch
        self.bm = beatmatch
        self.tmp = Path(tempfile.mkdtemp())
        patcher = mock.patch.object(beatmatch, "CACHE", self.tmp / "bpm.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_speed_for_basic_ratio(self):
        self.assertAlmostEqual(self.bm.speed_for(105, 100), 1.05, places=3)
        self.assertAlmostEqual(self.bm.speed_for(100, 105), 1 / 1.05, places=3)

    def test_speed_for_none_cases(self):
        self.assertIsNone(self.bm.speed_for(None, 100))
        self.assertIsNone(self.bm.speed_for(100, None))
        self.assertIsNone(self.bm.speed_for(100, 0))

    def test_speed_for_clamps_far_tempos(self):
        self.assertIsNone(self.bm.speed_for(120, 90))    # +33% — too far
        self.assertIsNone(self.bm.speed_for(90, 130))    # -31% — too far

    def test_speed_for_uses_half_double_time_feel(self):
        # 170 vs 85 is the same groove double-time; ratio 2.0 -> halved to 1.0
        self.assertAlmostEqual(self.bm.speed_for(170, 85), 1.0, places=6)
        # 85 vs 170: 0.5 -> doubled to 1.0
        self.assertAlmostEqual(self.bm.speed_for(85, 170), 1.0, places=6)

    def test_cache_roundtrip_and_staleness(self):
        f = self.tmp / "song.mp3"
        f.write_bytes(b"x")
        self.assertIsNone(self.bm.cached_bpm(str(f)))
        run_result = mock.Mock(stdout="120.0\n")
        with mock.patch.object(self.bm.subprocess, "run", return_value=run_result):
            bpm = self.bm.analyze(str(f))
        self.assertEqual(bpm, 120.0)
        self.assertEqual(self.bm.cached_bpm(str(f)), 120.0)
        # mtime change invalidates
        f.write_bytes(b"y")
        import os as _os
        m = f.stat().st_mtime + 10
        _os.utime(f, (m, m))
        self.assertIsNone(self.bm.cached_bpm(str(f)))


class LLMURLGuard(unittest.TestCase):
    def test_loopback_literals_allowed(self):
        from dj import llm
        for url in ("http://127.0.0.1:8080/v1/chat/completions",
                    "http://[::1]:8080/v1/chat/completions",
                    "http://localhost:11434/api/chat"):
            llm._assert_safe(url)  # must not raise
        llm._assert_safe("https://api.openai.com/v1/chat/completions")

    def test_remote_blocked(self):
        from dj import llm
        for url in ("http://evil.com:8080/x", "https://evil.com/y",
                    "ftp://127.0.0.1/z", "http://192.168.1.5:8080/x"):
            self.assertRaises(ValueError, llm._assert_safe, url)


class MPRIS(unittest.TestCase):
    def test_playback_status_mapping(self):
        from dj import mpris
        self.assertEqual(mpris.playback_status(True), "Playing")
        self.assertEqual(mpris.playback_status(False), "Stopped")

    def test_metadata_builder(self):
        from dj import mpris
        d = mpris.metadata_for("Nightmare")
        self.assertEqual(d["xesam:title"], "Nightmare")
        self.assertEqual(d["xesam:artist"], ["DJ-K"])
        # empty title still shows a sane label
        self.assertEqual(mpris.metadata_for(None)["xesam:title"], "DJ-K")


def _strip_settings_env(case):
    """Remove ambient settings env vars so tests never read the developer's
    shell (DJ_* plus the two non-DJ settings keys)."""
    saved = {k: v for k, v in os.environ.items()
             if k.startswith("DJ_") or k in ("OPENAI_API_KEY", "OLLAMA_URL")}
    for k in saved:
        del os.environ[k]
    case.addCleanup(os.environ.update, saved)


class Settings(unittest.TestCase):
    def setUp(self):
        from dj import settings
        self.s = settings
        _strip_settings_env(self)
        self.tmp = Path(tempfile.mkdtemp())
        patcher = mock.patch.object(settings, "FILE", self.tmp / "settings.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_defaults(self):
        self.assertTrue(self.s.resolve("crossfade"))
        self.assertEqual(self.s.resolve("provider"), "auto")
        self.assertEqual(self.s.resolve("llm_timeout"), 300)

    def test_roundtrip_and_live_flag(self):
        self.s.update({"crossfade": False, "ollama_model": "llama3"})
        self.assertFalse(self.s.crossfade())
        self.assertEqual(self.s.resolve("ollama_model"), "llama3")

    def test_env_overrides_file(self):
        self.s.update({"crossfade": True})
        os.environ["DJ_CROSSFADE"] = "0"
        try:
            self.assertFalse(self.s.resolve("crossfade"))
        finally:
            del os.environ["DJ_CROSSFADE"]

    def test_coercion(self):
        self.s.update({"llm_timeout": "120", "beatmatch": "off"})
        self.assertEqual(self.s.resolve("llm_timeout"), 120)
        self.assertFalse(self.s.resolve("beatmatch"))

    def test_unknown_key_rejected(self):
        self.assertRaises(KeyError, self.s.update, {"nope": 1})

    def test_mask(self):
        self.assertEqual(self.s.mask(""), "")
        self.assertIn("…", self.s.mask("sk-abcdef1234567890"))
        self.assertNotIn("abcdef", self.s.mask("sk-abcdef1234567890"))

    def test_restart_keys_marked(self):
        self.assertNotIn("provider", self.s.RESTART_KEYS)  # llm.chat resolves it per call
        self.assertNotIn("openai_api_key", self.s.RESTART_KEYS)  # resolved per call too
        self.assertNotIn("crossfade", self.s.RESTART_KEYS)
        self.assertIn("mpris", self.s.RESTART_KEYS)
        self.assertNotIn("source_local", self.s.RESTART_KEYS)


class SourceToggles(unittest.TestCase):
    def setUp(self):
        from dj import settings
        self.settings = settings
        _strip_settings_env(self)
        patcher = mock.patch.object(settings, "FILE", Path(tempfile.mkdtemp()) / "settings.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_source_toggles_live(self):
        # hermetic: no real file/env — defaults must be on and boolean
        self.assertIs(self.settings.source_local(), True)
        self.assertIs(self.settings.source_youtube(), True)

    def test_enqueue_smart_respects_sources(self):
        from dj.main import enqueue_smart
        lib = [{"path": "/x/a.mp3", "name": "a"}]

        class FakePlayer:
            def __init__(self):
                self.q = []
            def enqueue(self, src, title=""):
                self.q.append((src, title))

        # local off -> local hit skipped, falls to YouTube (mocked — no network)
        p = FakePlayer()
        with mock.patch.object(self.settings, "source_local", lambda: False), \
             mock.patch.object(self.settings, "source_youtube", lambda: True), \
             mock.patch("dj.mpvproc.resolve_youtube",
                        return_value=("https://resolved/audio", "a")):
            enqueue_smart(p, lib, ["a", "zzz no such song"])
        assert_sources = [s for s, _ in p.q]
        self.assertNotIn("/x/a.mp3", assert_sources)
        self.assertIn("https://resolved/audio", assert_sources)   # first resolved now
        self.assertIn(("ytq:zzz no such song", "zzz no such song"), p.q)  # rest deferred

        # youtube off -> non-local queries skipped entirely
        p2 = FakePlayer()
        with mock.patch.object(self.settings, "source_local", lambda: True), \
             mock.patch.object(self.settings, "source_youtube", lambda: False), \
             mock.patch("dj.mpvproc.resolve_youtube",
                        side_effect=AssertionError("yt used while disabled")):
            enqueue_smart(p2, lib, ["a", "zzz no such song"])
        self.assertEqual(p2.q, [("/x/a.mp3", "a")])

        # both off -> nothing enqueued, no crash
        p3 = FakePlayer()
        with mock.patch.object(self.settings, "source_local", lambda: False), \
             mock.patch.object(self.settings, "source_youtube", lambda: False):
            enqueue_smart(p3, lib, ["a"])
        self.assertEqual(p3.q, [])

    def test_brain_hint_omits_library_when_local_off(self):
        lib_hint = [{"name": "song", "path": "/x"}]
        captured = {}
        with mock.patch.object(djbrain.llm, "chat",
                               lambda m: (captured.update(last=m[-1]["content"]) or
                                          '{"reply":"ok","action":"chat","tracks":[]}')):
            with mock.patch.object(self.settings, "source_local", lambda: False):
                djbrain.think("hi", tracks_hint=lib_hint)
        self.assertNotIn("Local library:", captured["last"])
        self.assertIn("Sources available", captured["last"])
        with mock.patch.object(djbrain.llm, "chat",
                               lambda m: (captured.update(last=m[-1]["content"]) or
                                          '{"reply":"ok","action":"chat","tracks":[]}')):
            with mock.patch.object(self.settings, "source_local", lambda: True):
                djbrain.think("hi", tracks_hint=lib_hint)
        self.assertIn("Local library:", captured["last"])


class AuditFixes(unittest.TestCase):
    """Second audit round: crash guards, CSRF, pause state, env coercion."""

    def test_mpv_missing_raises_valueerror(self):
        # FileNotFoundError from Popen must surface as ValueError at the choke
        # point, so every existing ValueError handler keeps working.
        def fake_popen(*a, **kw):
            raise FileNotFoundError("mpv")

        with tempfile.NamedTemporaryFile(suffix=".mp3") as f, \
             mock.patch.object(mpvproc.subprocess, "Popen", fake_popen):
            self.assertRaises(ValueError, mpvproc.launch, "/tmp/s.sock", 100, f.name)

    def test_tray_noop_when_disabled_or_no_gi(self):
        from dj import tray
        with mock.patch.object(tray, "_indicator_module", lambda: None):
            self.assertIsNone(tray.start(None, "x"))  # no gi -> no crash
        with mock.patch.object(tray.settings, "tray", lambda: False):
            self.assertIsNone(tray.start(None, "x"))  # toggle honored

    def test_djbrain_coerces_null_reply(self):
        d = djbrain._parse('{"reply": null, "action": "chat", "tracks": []}')
        self.assertEqual(d["reply"], "")

    def test_settings_bad_env_int_falls_back(self):
        from dj import settings
        os.environ["DJ_LLM_TIMEOUT"] = "abc"
        try:
            self.assertEqual(settings.resolve("llm_timeout"), 300)
        finally:
            del os.environ["DJ_LLM_TIMEOUT"]

    def test_settings_new_schema_keys(self):
        from dj import settings
        self.assertEqual(settings.resolve("llamacpp_model"), "local")
        self.assertEqual(settings.resolve("web_port"), 8090)
        self.assertEqual(settings.resolve("gen_python"), "")
        self.assertIn("web_port", settings.RESTART_KEYS)

    def test_settings_atomic_update_leaves_no_tmp(self):
        from dj import settings
        tmp = Path(tempfile.mkdtemp())
        with mock.patch.object(settings, "FILE", tmp / "settings.json"):
            settings.update({"crossfade": False})
            self.assertFalse(settings.crossfade())
            self.assertEqual(list(tmp.iterdir()), [tmp / "settings.json"])

    def test_status_reports_paused(self):
        from dj.player import Player
        p = Player.__new__(Player)  # skip __init__ (it starts the advance thread)
        p.queue, p.proc, p.sock_path = [], None, None
        p.current = p.current_source = None
        p._pre_duck = 100

        def fake_query(sock, cmd, timeout=1.0):
            if cmd[1] == "pause":
                return {"error": "success", "data": True}
            return None

        with mock.patch.object(Player, "_ipc_query",
                               staticmethod(fake_query)):
            self.assertTrue(p.status()["paused"])

        def false_query(sock, cmd, timeout=1.0):
            if cmd[1] == "pause":
                return {"error": "success", "data": False}
            return None

        with mock.patch.object(Player, "_ipc_query",
                               staticmethod(false_query)):
            self.assertFalse(p.status()["paused"])

    def test_cross_site_guard(self):
        from dj.web import cross_site
        self.assertFalse(cross_site({}))  # curl / header-less clients pass
        self.assertFalse(cross_site({"Origin": "http://127.0.0.1:8090"}))
        self.assertFalse(cross_site({"Origin": "http://localhost:8090"}))
        self.assertFalse(cross_site({"Sec-Fetch-Site": "same-origin"}))
        self.assertTrue(cross_site({"Origin": "https://evil.com"}))
        self.assertTrue(cross_site({"Origin": "http://evil.com:8090"}))
        self.assertTrue(cross_site({"Origin": "null"}))
        self.assertTrue(cross_site({"Sec-Fetch-Site": "cross-site"}))

    def test_mpris_paused_mapping(self):
        from dj import mpris
        self.assertEqual(mpris.playback_status(True, True), "Paused")
        self.assertEqual(mpris.playback_status(True, False), "Playing")
        self.assertEqual(mpris.playback_status(False, True), "Stopped")


class AuditRound3(unittest.TestCase):
    """Third audit round: crossfade both ramps, leaks, duck at zero, web hardening."""

    def test_duck_restores_zero_volume(self):
        # volume 0 is real — `or 100` used to stomp the listener's mute
        from dj.player import Player
        p = Player.__new__(Player)
        p._pre_duck = 100
        p._duck_depth = 0
        p.sock_path = "/nonexistent.sock"
        sent = []
        with mock.patch.object(Player, "_ipc",
                               staticmethod(lambda sock, cmd: sent.append(cmd))), \
             mock.patch.object(p, "volume", lambda: 0):
            p.duck(True)
            p.duck(False)
        self.assertEqual(sent[-1], ["set_property", "volume", 0])
        self.assertEqual(sent[0], ["set_property", "volume", 25])

    def test_nested_duck_keeps_real_pre_duck_level(self):
        # two overlapping DJ lines: the second duck must not snapshot the
        # already-ducked 25 as the restore target (music stayed quiet forever)
        from dj.player import Player
        p = Player.__new__(Player)
        p._pre_duck = 100
        p._duck_depth = 0
        p.sock_path = "/nonexistent.sock"
        sent = []
        with mock.patch.object(Player, "_ipc",
                               staticmethod(lambda sock, cmd: sent.append(cmd))), \
             mock.patch.object(p, "volume", lambda: 80):
            p.duck(True)   # A: 80 -> 25
            p.duck(True)   # B: already ducked — no second snapshot
            p.duck(False)  # A leaves: still ducked
            p.duck(False)  # B leaves: restore 80
        self.assertEqual(sent, [["set_property", "volume", 25],
                                ["set_property", "volume", 80]])

    def test_skip_stops_when_queue_was_all_dead_entries(self):
        from dj.player import Player
        p = Player.__new__(Player)
        p.queue = [("ytq:dead", "dead")]
        p._lock = threading.RLock()
        stopped = []
        with mock.patch.object(p, "_pop_and_play", return_value=False), \
             mock.patch.object(p, "_playing", return_value=True), \
             mock.patch.object(p, "stop", lambda: stopped.append(True)):
            p.skip()
        self.assertEqual(stopped, [True])

    def test_transition_speed_matches_effective_not_raw_tempo(self):
        # the outgoing track is playing at bpm × speed — chained transitions
        # must match its effective tempo or every crossfade compounds the drift
        from dj import beatmatch
        from dj.player import Player
        p = Player.__new__(Player)
        p.current_source = "/old.mp3"
        p.current_speed = 100.0 / 105.0  # launched matching 105→100: audibly 100 BPM now
        bpms = {"/old.mp3": 105.0, "/new.mp3": 100.0}
        with mock.patch.object(beatmatch, "cached_bpm", lambda s: bpms.get(s)):
            # raw 105 vs 100 would give 1.05 (drift); effective 100 vs 100 gives 1.0
            self.assertAlmostEqual(p._transition_speed("/new.mp3", True), 1.0, places=6)

    def test_sweep_removes_orphaned_temp_audio_only(self):
        from dj import tts
        tmp = Path(tempfile.mkdtemp())
        (tmp / "unrelated.wav").write_bytes(b"x")
        for name in ("djk-tts-abc.wav", "djgen-xyz.wav"):
            (tmp / name).write_bytes(b"x")
            (tmp / (name + ".sock")).write_bytes(b"x")
        (tmp / "djjamal-deadbeef.sock").write_bytes(b"x")  # leaked player IPC socket
        with mock.patch.object(tts.tempfile, "gettempdir", lambda: str(tmp)):
            tts.sweep_temp_audio()
        self.assertTrue((tmp / "unrelated.wav").exists())
        self.assertFalse((tmp / "djk-tts-abc.wav").exists())
        self.assertFalse((tmp / "djk-tts-abc.wav.sock").exists())
        self.assertFalse((tmp / "djgen-xyz.wav").exists())
        self.assertFalse((tmp / "djgen-xyz.wav.sock").exists())
        self.assertFalse((tmp / "djjamal-deadbeef.sock").exists())


class AuditRound4(unittest.TestCase):
    """Fourth audit round: bpm-entry guard, empty-tracks downgrade, metadata spec."""

    def setUp(self):
        from dj import beatmatch
        self.bm = beatmatch
        self.tmp = Path(tempfile.mkdtemp())
        patcher = mock.patch.object(beatmatch, "CACHE", self.tmp / "bpm.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_bpm_cache_garbage_entry_does_not_crash(self):
        from dj import beatmatch
        f = self.tmp / "song.mp3"
        f.write_bytes(b"x")
        for bad in ("3.5", '{}', '{"bpm": "fast"}', '{"bpm": 120}', '[1,2]'):
            beatmatch.CACHE.write_text(json.dumps({str(f): bad}))
            self.assertIsNone(beatmatch.cached_bpm(str(f)))
        beatmatch.CACHE.write_text(json.dumps(
            {str(f): {"bpm": 128.0, "mtime": f.stat().st_mtime}}))
        self.assertEqual(beatmatch.cached_bpm(str(f)), 128.0)

    def test_playback_action_with_no_tracks_downgrades_to_chat(self):
        d = djbrain._parse('{"reply": "cranking it!", "action": "play", "tracks": null}')
        self.assertEqual(d["action"], "chat")
        d = djbrain._parse('{"reply": "ok", "action": "generate", "tracks": []}')
        self.assertEqual(d["action"], "chat")
        d = djbrain._parse('{"reply": "ok", "action": "queue", "tracks": ["a"]}')
        self.assertEqual(d["action"], "queue")  # real tracks keep the action

    def test_ytdl_scheme_no_longer_allowed(self):
        self.assertRaises(ValueError, mpvproc.validate_source, "ytdl:song")

    def test_metadata_carries_trackid_and_length(self):
        from dj import mpris
        d = mpris.metadata_for("Nightmare", duration=213.5)
        self.assertTrue(d["mpris:trackid"].startswith("/org/mpris/MediaPlayer2"))
        self.assertEqual(d["mpris:length"], int(213.5 * mpris.MICROSECONDS))
        self.assertNotIn("mpris:length", mpris.metadata_for("Nightmare"))


if __name__ == "__main__":
    unittest.main()
