from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anime_vault.repository import (
    ensure_database,
    load_privacy_settings,
    save_access_password,
    verify_access_password,
)


class AccessPasswordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "anime.db"
        self.db_patch = patch("anime_vault.repository.DB_PATH", self.db_path)
        self.db_patch.start()
        ensure_database()

    def tearDown(self) -> None:
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_password_is_hashed_and_can_be_verified(self) -> None:
        save_access_password("correct horse")

        settings = load_privacy_settings()
        self.assertIsNotNone(settings)
        self.assertNotEqual(settings["password_hash"], b"correct horse")
        self.assertTrue(verify_access_password("correct horse"))
        self.assertFalse(verify_access_password("wrong horse"))

    def test_changing_password_rotates_the_session_secret(self) -> None:
        save_access_password("first password")
        first_secret = load_privacy_settings()["session_secret"]

        save_access_password("second password")
        second_secret = load_privacy_settings()["session_secret"]

        self.assertNotEqual(first_secret, second_secret)
        self.assertFalse(verify_access_password("first password"))
        self.assertTrue(verify_access_password("second password"))


if __name__ == "__main__":
    unittest.main()
