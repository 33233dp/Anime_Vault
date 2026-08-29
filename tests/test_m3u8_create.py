from __future__ import annotations

import http.client
import tempfile
import threading
import unittest
from urllib.parse import urlencode
from pathlib import Path
from unittest.mock import patch

from anime_vault.repository import ensure_database, get_anime, load_catalog
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
        self.assertEqual(len(anime["playlist_episodes"]), 2)
        self.assertIn("%5B01%5D.mp4", anime["playlist_episodes"][0]["url"])

    def test_url_list_can_create_and_parse_anime_without_images(self) -> None:
        fields = {
            "slug": "url-list-test",
            "title": "URL 番剧",
            "resource_type": "url_list",
            "url_list_text": "https://media.example.test/1.mp4\nhttps://media.example.test/2.mp4",
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
        self.assertEqual(anime["playlist_episodes"][0]["title"], "URL 番剧-第一集")


if __name__ == "__main__":
    unittest.main()
