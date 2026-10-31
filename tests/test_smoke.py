"""Smoke tests: pure logic only — no mpv, no audio, no network, no LLM."""
import json
import os
import subprocess
import sys
import tempfile
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
        d = djbrain._parse('Sure! {"reply": "hi", "action": "queue", "tracks": []}')
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


if __name__ == "__main__":
    unittest.main()
