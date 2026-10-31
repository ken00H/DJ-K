"""Smoke tests: pure logic only — no mpv, no audio, no network, no LLM."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dj import djbrain, library, mpvproc  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
