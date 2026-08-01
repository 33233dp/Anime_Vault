from __future__ import annotations

import unittest

from anime_vault.playlists import parse_m3u8_upload


class ParseM3U8UploadTests(unittest.TestCase):
    def test_dr_stone_sample_generates_24_episodes(self) -> None:
        sample_lines = ["#EXTM3U", "#PLAYLIST:石纪元 第一季 (2019)"]
        for episode in range(1, 25):
            sample_lines.extend(
                [
                    f"#EXTINF:-1,石纪元 第一季 - 第{episode:02d}集",
                    f"https://media.example.test/episode-{episode:02d}.mp4",
                ]
            )

        episodes = parse_m3u8_upload("Dr.STONE_S01.m3u8", "\n".join(sample_lines).encode())

        self.assertEqual(len(episodes), 24)
        self.assertEqual(episodes[0]["title"], "石纪元 第一季 - 第01集")
        self.assertEqual(episodes[-1]["title"], "石纪元 第一季 - 第24集")
        self.assertTrue(episodes[0]["url"].startswith("https://media.example.test/"))

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
