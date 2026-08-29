from __future__ import annotations

import http.client
import os
import tempfile
import threading
import unittest
from urllib.parse import urlencode
from pathlib import Path
from unittest.mock import patch

from anime_vault.repository import ensure_database, get_anime, load_catalog
from anime_vault.renderers import render_episode_section
from anime_vault.server import create_server


def multipart_payload(
    fields: dict[str, str],
    filename: str,
    file_payload: bytes,
) -> tuple[bytes, str]:
    boundary = "anime-vault-test-boundary"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                'Content-Disposition: form-data; name="playlist_file"; '
                f'filename="{filename}"\r\n'
            ).encode(),
            b"Content-Type: application/vnd.apple.mpegurl\r\n\r\n",
            file_payload,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), boundary


class CreateM3U8AnimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "anime.db"
        self.db_patch = patch("anime_vault.repository.DB_PATH", self.db_path)
        self.db_patch.start()
        ensure_database()
        self.server = create_server("127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        load_catalog.cache_clear()
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_playlist_can_create_anime_without_poster_or_still(self) -> None:
        playlist = (
            "#EXTM3U\n"
            "#EXTINF:-1,石纪元 第01集\n"
            "https://media.example.test/动漫/[01].mp4\n"
            "#EXTINF:-1,石纪元 第02集\n"
            "https://media.example.test/动漫/[02].mp4\n"
        ).encode("utf-8")
        payload, boundary = multipart_payload(
            {
                "slug": "dr-stone-playlist-test",
                "title": "石纪元 第一季",
                "resource_type": "playlist",
                "playback_mode": "online",
                "playlist_episode_offset": "3",
            },
            "dr-stone.m3u8",
            playlist,
        )

        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5
        )
        connection.request(
            "POST",
            "/anime/create",
            body=payload,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        response = connection.getresponse()
        response.read()
        connection.close()

        self.assertEqual(response.status, 303)
        self.assertEqual(response.getheader("Location"), "/anime/dr-stone-playlist-test")
        anime = get_anime("dr-stone-playlist-test")
        self.assertIsNotNone(anime)
        self.assertEqual(anime["poster_path"], "")
        self.assertEqual(anime["still_path"], "")
        self.assertEqual(anime["episode_count"], 2)
        self.assertEqual(anime["playlist_episode_offset"], 3)
        self.assertEqual(len(anime["playlist_episodes"]), 2)
        self.assertIn("%5B01%5D.mp4", anime["playlist_episodes"][0]["url"])
        episode_section = render_episode_section(anime)
        self.assertIn('<span class="episode-card__roman">4</span>', episode_section)
        self.assertIn("第 4 集", episode_section)
        self.assertIn('/anime/dr-stone-playlist-test/episode/1', episode_section)

        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5
        )
        connection.request("GET", "/animeko/anime/dr-stone-playlist-test")
        response = connection.getresponse()
        detail_page = response.read().decode("utf-8")
        connection.close()

        self.assertEqual(response.status, 200)
        self.assertIn(">第 4 集<", detail_page)
        self.assertIn("https://media.example.test/%E5%8A%A8%E6%BC%AB/%5B01%5D.mp4", detail_page)

    def test_homepage_has_animeko_subscription_copy_url(self) -> None:
        with patch.dict(os.environ, {"ANIMEKO_API_TOKEN": "12345678"}):
            connection = http.client.HTTPConnection(
                "127.0.0.1", self.server.server_address[1], timeout=5
            )
            connection.request(
                "GET",
                "/",
                headers={"Host": "192.168.0.111:8000"},
            )
            response = connection.getresponse()
            homepage = response.read().decode("utf-8")
            connection.close()

        self.assertEqual(response.status, 200)
        self.assertIn("一键复制animeko订阅", homepage)
        self.assertIn(
            'data-copy-value="http://192.168.0.111:8000/animeko/subscription?token=12345678"',
            homepage,
        )

    def test_url_list_can_create_and_parse_anime_without_images(self) -> None:
        fields = {
            "slug": "url-list-test",
            "title": "URL 番剧",
            "resource_type": "url_list",
            "url_list_text": "https://media.example.test/1.mp4\nhttps://media.example.test/2.mp4",
            "playlist_episode_offset": "3",
        }
        payload = urlencode(fields).encode("utf-8")
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5
        )
        connection.request(
            "POST",
            "/anime/create",
            body=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(payload)),
            },
        )   
        response = connection.getresponse()
        response.read()
        connection.close()

        self.assertEqual(response.status, 303)
        anime = get_anime("url-list-test")
        self.assertIsNotNone(anime)
        self.assertEqual(anime["resource_type"], "playlist")
        self.assertEqual(anime["episode_count"], 2)
        self.assertEqual(anime["playlist_episode_offset"], 3)
        self.assertEqual(anime["playlist_episodes"][0]["title"], "URL 番剧-第四集")
        episode_section = render_episode_section(anime)
        self.assertIn('<span class="episode-card__roman">4</span>', episode_section)
        self.assertIn("第 4 集", episode_section)

        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5
        )
        connection.request("GET", "/anime/url-list-test")
        response = connection.getresponse()
        detail_page = response.read().decode("utf-8")
        connection.close()

        self.assertEqual(response.status, 200)
        self.assertIn("删除番剧", detail_page)
        self.assertIn("/anime/url-list-test/delete", detail_page)

        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5
        )
        connection.request("POST", "/anime/url-list-test/delete", body=b"")
        response = connection.getresponse()
        response.read()
        connection.close()

        self.assertEqual(response.status, 303)
        self.assertEqual(response.getheader("Location"), "/")
        self.assertIsNone(get_anime("url-list-test"))

    def test_multipart_url_list_preserves_chinese_text_and_encodes_path(self) -> None:
        playlist = (
            "#EXTM3U\n"
            "#EXTINF:-1,我是大哥大-第一集\n"
            "http://192.168.0.111:5244/d/树莓派/我是大哥大/我是大哥大01.mp4?sign=abc=:0\n"
        ).encode("utf-8")
        payload, boundary = multipart_payload(
            {
                "slug": "chinese-url-test",
                "title": "我是大哥大",
                "resource_type": "url_list",
                "url_list_text": "http://192.168.0.111:5244/d/树莓派/我是大哥大/我是大哥大01.mp4?sign=abc=:0",
            },
            "chinese.m3u8",
            playlist,
        )
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5
        )
        connection.request(
            "POST",
            "/anime/create",
            body=payload,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        response = connection.getresponse()
        response.read()
        connection.close()

        self.assertEqual(response.status, 303)
        anime = get_anime("chinese-url-test")
        self.assertIsNotNone(anime)
        self.assertEqual(anime["title"], "我是大哥大")
        self.assertIn("%E6%A0%91%E8%8E%93%E6%B4%BE", anime["playlist_episodes"][0]["url"])
        self.assertIn("%E6%88%91%E6%98%AF%E5%A4%A7%E5%93%A5%E5%A4%A701.mp4", anime["playlist_episodes"][0]["url"])


if __name__ == "__main__":
    unittest.main()
