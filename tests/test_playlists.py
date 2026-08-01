from __future__ import annotations

import unittest
from pathlib import Path

from anime_vault.playlists import parse_m3u8_upload


class ParseM3U8UploadTests(unittest.TestCase):
    def test_dr_stone_sample_generates_24_episodes(self) -> None:
        path = Path(__file__).resolve().parents[1] / "m3u8" / "Dr.STONE_S01.m3u8"

        episodes = parse_m3u8_upload(path.name, path.read_bytes())

        self.assertEqual(len(episodes), 24)
        self.assertEqual(episodes[0]["title"], "石纪元 第一季 - 第01集")
        self.assertEqual(episodes[-1]["title"], "石纪元 第一季 - 第24集")
        self.assertTrue(episodes[0]["url"].startswith("http://192.168.0.111:5244/"))

    def test_rejects_non_m3u8_extension(self) -> None:
        with self.assertRaisesRegex(ValueError, r"\.m3u8"):
            parse_m3u8_upload("episodes.txt", b"#EXTM3U\nhttps://example.com/1.mp4")

    def test_rejects_relative_playback_address(self) -> None:
        with self.assertRaisesRegex(ValueError, "完整"):
            parse_m3u8_upload("episodes.m3u8", b"#EXTM3U\nvideo/1.mp4")

    def test_rejects_playlist_without_playback_address(self) -> None:
        with self.assertRaisesRegex(ValueError, "没有找到"):
            parse_m3u8_upload("episodes.m3u8", b"#EXTM3U\n#PLAYLIST:Empty")


if __name__ == "__main__":
    unittest.main()
