from __future__ import annotations

import unittest

from anime_vault.playlists import convert_urls_to_m3u8, parse_m3u8_upload


class ParseM3U8UploadTests(unittest.TestCase):
    def test_convert_urls_matches_script_numbering_and_prefix(self) -> None:
        payload = convert_urls_to_m3u8(
            "https://example.com/1.mp4\n\nhttps://example.com/2.mp4\n",
            "我推的孩子",
        )
        self.assertEqual(
            payload.decode(),
            "#EXTM3U\n"
            "#EXTINF:-1,我推的孩子-第一集\nhttps://example.com/1.mp4\n"
            "#EXTINF:-1,我推的孩子-第二集\nhttps://example.com/2.mp4\n",
        )
        episodes = parse_m3u8_upload("generated.m3u8", payload)
        self.assertEqual(episodes[1]["title"], "我推的孩子-第二集")

    def test_convert_urls_applies_episode_offset_to_generated_titles(self) -> None:
        payload = convert_urls_to_m3u8(
            "https://example.com/1.mp4\nhttps://example.com/2.mp4",
            "番剧",
            3,
        )

        self.assertIn("#EXTINF:-1,番剧-第四集", payload.decode())
        self.assertIn("#EXTINF:-1,番剧-第五集", payload.decode())

    def test_convert_urls_normalizes_invalid_or_negative_offset(self) -> None:
        self.assertIn(
            "#EXTINF:-1,番剧-第一集",
            convert_urls_to_m3u8("https://example.com/1.mp4", "番剧", -3).decode(),
        )
        self.assertIn(
            "#EXTINF:-1,番剧-第一集",
            convert_urls_to_m3u8("https://example.com/1.mp4", "番剧", "invalid").decode(),
        )

    def test_convert_urls_requires_at_least_one_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "未提供"):
            convert_urls_to_m3u8("\n  ", "番剧")

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

    def test_encodes_unicode_and_square_brackets_in_playback_url(self) -> None:
        payload = (
            "#EXTM3U\n"
            "#EXTINF:-1,第 1 集\n"
            "http://media.example.test/动漫/[Group][01].mp4?sign=a:b\n"
        ).encode()

        episodes = parse_m3u8_upload("episodes.m3u8", payload)

        self.assertIn("%E5%8A%A8%E6%BC%AB", episodes[0]["url"])
        self.assertIn("%5BGroup%5D%5B01%5D.mp4", episodes[0]["url"])
        self.assertTrue(episodes[0]["url"].endswith("?sign=a:b"))


if __name__ == "__main__":
    unittest.main()
