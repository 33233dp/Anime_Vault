from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from functools import lru_cache
from typing import Any

from .config import DB_PATH, DEFAULT_MEDIA_LIBRARY_DIRS
from .seed import CATALOG_SEED


PASSWORD_HASH_ITERATIONS = 600_000


def ensure_database() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        media_library_table_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'media_library_directory'
            """
        ).fetchone() is not None
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS anime (
                slug TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                subtitle TEXT NOT NULL,
                release_info TEXT NOT NULL,
                studio TEXT NOT NULL,
                synopsis TEXT NOT NULL,
                cast_json TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                poster_path TEXT NOT NULL,
                still_path TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                playback_url TEXT NOT NULL DEFAULT '',
                playback_mode TEXT NOT NULL DEFAULT 'online',
                local_media_dir TEXT NOT NULL DEFAULT '',
                episode_count INTEGER NOT NULL DEFAULT 0,
                episode_root_domain TEXT NOT NULL DEFAULT '',
                episode_route TEXT NOT NULL DEFAULT '',
                episode_query_prefix TEXT NOT NULL DEFAULT '',
                episode_start_number INTEGER NOT NULL DEFAULT 1,
                episode_other TEXT NOT NULL DEFAULT '',
                resource_type TEXT NOT NULL DEFAULT 'link',
                playlist_name TEXT NOT NULL DEFAULT '',
                playlist_episodes_json TEXT NOT NULL DEFAULT '[]',
                playlist_episode_offset INTEGER NOT NULL DEFAULT 0,
                last_played_episode INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        ensure_column(connection, "anime", "playback_url", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "anime", "playback_mode", "TEXT NOT NULL DEFAULT 'online'")
        ensure_column(connection, "anime", "local_media_dir", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "anime", "episode_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(
            connection, "anime", "episode_root_domain", "TEXT NOT NULL DEFAULT ''"
        )
        ensure_column(connection, "anime", "episode_route", "TEXT NOT NULL DEFAULT ''")
        ensure_column(
            connection, "anime", "episode_query_prefix", "TEXT NOT NULL DEFAULT ''"
        )
        ensure_column(
            connection, "anime", "episode_start_number", "INTEGER NOT NULL DEFAULT 1"
        )
        ensure_column(connection, "anime", "episode_other", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "anime", "resource_type", "TEXT NOT NULL DEFAULT 'link'")
        ensure_column(connection, "anime", "playlist_name", "TEXT NOT NULL DEFAULT ''")
        ensure_column(
            connection, "anime", "playlist_episodes_json", "TEXT NOT NULL DEFAULT '[]'"
        )
        ensure_column(
            connection, "anime", "playlist_episode_offset", "INTEGER NOT NULL DEFAULT 0"
        )
        ensure_column(
            connection, "anime", "last_played_episode", "INTEGER NOT NULL DEFAULT 0"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS episode_playback_progress (
                slug TEXT NOT NULL,
                episode_number INTEGER NOT NULL,
                position_seconds REAL NOT NULL DEFAULT 0,
                duration_seconds REAL NOT NULL DEFAULT 0,
                completed INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                PRIMARY KEY (slug, episode_number)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS anime_playback_activity (
                slug TEXT PRIMARY KEY,
                qualified_played_at REAL NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS media_library_directory (
                path TEXT PRIMARY KEY,
                position INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS privacy_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                password_salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                password_iterations INTEGER NOT NULL,
                session_secret BLOB NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        if not media_library_table_exists:
            connection.executemany(
                "INSERT INTO media_library_directory (path, position) VALUES (?, ?)",
                [
                    (path.as_posix(), position)
                    for position, path in enumerate(DEFAULT_MEDIA_LIBRARY_DIRS)
                ],
            )
        connection.executemany(
            """
            INSERT INTO anime (
                slug,
                title,
                subtitle,
                release_info,
                studio,
                synopsis,
                cast_json,
                keywords_json,
                poster_path,
                still_path,
                sources_json,
                playback_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                title = excluded.title,
                subtitle = excluded.subtitle,
                release_info = excluded.release_info,
                studio = excluded.studio,
                synopsis = excluded.synopsis,
                cast_json = excluded.cast_json,
                keywords_json = excluded.keywords_json,
                poster_path = excluded.poster_path,
                still_path = excluded.still_path,
                sources_json = excluded.sources_json
            """,
            [
                (
                    anime["slug"],
                    anime["title"],
                    anime["subtitle"],
                    anime["release_info"],
                    anime["studio"],
                    anime["synopsis"],
                    json.dumps(anime["cast"], ensure_ascii=False),
                    json.dumps(anime["keywords"], ensure_ascii=False),
                    anime["poster_path"],
                    anime["still_path"],
                    json.dumps(anime["sources"], ensure_ascii=False),
                    "",
                )
                for anime in CATALOG_SEED
            ],
        )
        connection.commit()
    load_catalog.cache_clear()


def load_privacy_settings() -> dict[str, Any] | None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM privacy_settings WHERE id = 1"
        ).fetchone()
    return dict(row) if row is not None else None


def save_access_password(password: str) -> None:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            INSERT INTO privacy_settings (
                id,
                password_salt,
                password_hash,
                password_iterations,
                session_secret,
                updated_at
            ) VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                password_salt = excluded.password_salt,
                password_hash = excluded.password_hash,
                password_iterations = excluded.password_iterations,
                session_secret = excluded.session_secret,
                updated_at = excluded.updated_at
            """,
            (
                salt,
                password_hash,
                PASSWORD_HASH_ITERATIONS,
                secrets.token_bytes(32),
                time.time(),
            ),
        )
        connection.commit()


def verify_access_password(password: str) -> bool:
    settings = load_privacy_settings()
    if settings is None:
        return False
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes(settings["password_salt"]),
        int(settings["password_iterations"]),
    )
    return secrets.compare_digest(password_hash, bytes(settings["password_hash"]))


def ensure_column(
    connection: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def load_media_library_paths() -> list[str]:
    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(
            "SELECT path FROM media_library_directory ORDER BY position, path"
        ).fetchall()
    return [str(row[0]) for row in rows]


def save_media_library_paths(paths: list[str]) -> None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("DELETE FROM media_library_directory")
        connection.executemany(
            "INSERT INTO media_library_directory (path, position) VALUES (?, ?)",
            [(path, position) for position, path in enumerate(paths)],
        )
        connection.commit()


@lru_cache(maxsize=1)
def load_catalog() -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM anime ORDER BY title COLLATE NOCASE"
        ).fetchall()

    catalog: list[dict[str, Any]] = []
    for row in rows:
        catalog.append(
            {
                **dict(row),
                "cast": json.loads(row["cast_json"]),
                "keywords": json.loads(row["keywords_json"]),
                "sources": json.loads(row["sources_json"]),
                "playlist_episodes": json.loads(row["playlist_episodes_json"] or "[]"),
            }
        )
    return catalog


def get_anime(slug: str) -> dict[str, Any] | None:
    for anime in load_catalog():
        if anime["slug"] == slug:
            return anime
    return None


def anime_exists(slug: str) -> bool:
    return get_anime(slug) is not None


def create_anime(record: dict[str, Any]) -> None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            INSERT INTO anime (
                slug,
                title,
                subtitle,
                release_info,
                studio,
                synopsis,
                cast_json,
                keywords_json,
                poster_path,
                still_path,
                sources_json,
                playback_url,
                playback_mode,
                local_media_dir,
                episode_count,
                episode_root_domain,
                episode_route,
                episode_query_prefix,
                episode_start_number,
                episode_other,
                resource_type,
                playlist_name,
                playlist_episodes_json,
                playlist_episode_offset,
                last_played_episode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["slug"],
                record["title"],
                record["subtitle"],
                record["release_info"],
                record["studio"],
                record["synopsis"],
                json.dumps(record["cast"], ensure_ascii=False),
                json.dumps(record["keywords"], ensure_ascii=False),
                record["poster_path"],
                record["still_path"],
                json.dumps(record["sources"], ensure_ascii=False),
                record["playback_url"],
                record["playback_mode"],
                record["local_media_dir"],
                record["episode_count"],
                record["episode_root_domain"],
                record["episode_route"],
                record["episode_query_prefix"],
                record["episode_start_number"],
                record["episode_other"],
                record["resource_type"],
                record["playlist_name"],
                json.dumps(record["playlist_episodes"], ensure_ascii=False),
                record["playlist_episode_offset"],
                record["last_played_episode"],
            ),
        )
        connection.commit()
    load_catalog.cache_clear()


def update_anime(slug: str, record: dict[str, Any]) -> None:
    with sqlite3.connect(DB_PATH) as connection:
        current_last_played = connection.execute(
            "SELECT last_played_episode FROM anime WHERE slug = ?",
            (slug,),
        ).fetchone()
        last_played = int(current_last_played[0]) if current_last_played else 0
        episode_count = int(record["episode_count"])
        if episode_count == 0 or last_played > episode_count:
            last_played = 0

        connection.execute(
            """
            UPDATE anime
            SET title = ?,
                subtitle = ?,
                release_info = ?,
                studio = ?,
                synopsis = ?,
                cast_json = ?,
                keywords_json = ?,
                poster_path = ?,
                still_path = ?,
                sources_json = ?,
                playback_url = ?,
                playback_mode = ?,
                local_media_dir = ?,
                episode_count = ?,
                episode_root_domain = ?,
                episode_route = ?,
                episode_query_prefix = ?,
                episode_start_number = ?,
                episode_other = ?,
                resource_type = ?,
                playlist_name = ?,
                playlist_episodes_json = ?,
                playlist_episode_offset = ?,
                last_played_episode = ?
            WHERE slug = ?
            """,
            (
                record["title"],
                record["subtitle"],
                record["release_info"],
                record["studio"],
                record["synopsis"],
                json.dumps(record["cast"], ensure_ascii=False),
                json.dumps(record["keywords"], ensure_ascii=False),
                record["poster_path"],
                record["still_path"],
                json.dumps(record["sources"], ensure_ascii=False),
                record["playback_url"],
                record["playback_mode"],
                record["local_media_dir"],
                episode_count,
                record["episode_root_domain"],
                record["episode_route"],
                record["episode_query_prefix"],
                record["episode_start_number"],
                record["episode_other"],
                record["resource_type"],
                record["playlist_name"],
                json.dumps(record["playlist_episodes"], ensure_ascii=False),
                record["playlist_episode_offset"],
                last_played,
                slug,
            ),
        )
        connection.commit()
    load_catalog.cache_clear()


def delete_anime(slug: str) -> bool:
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "DELETE FROM episode_playback_progress WHERE slug = ?",
            (slug,),
        )
        connection.execute(
            "DELETE FROM anime_playback_activity WHERE slug = ?",
            (slug,),
        )
        cursor = connection.execute("DELETE FROM anime WHERE slug = ?", (slug,))
        deleted = cursor.rowcount > 0
        connection.commit()
    load_catalog.cache_clear()
    return deleted


def save_playback_url(slug: str, playback_url: str) -> None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "UPDATE anime SET playback_url = ? WHERE slug = ?",
            (playback_url, slug),
        )
        connection.commit()
    load_catalog.cache_clear()


def save_episode_config(
    slug: str,
    episode_count: int,
    episode_root_domain: str,
    episode_route: str,
    episode_query_prefix: str,
    episode_start_number: int,
    episode_other: str,
    playback_mode: str,
    local_media_dir: str,
) -> None:
    with sqlite3.connect(DB_PATH) as connection:
        current_last_played = connection.execute(
            "SELECT last_played_episode FROM anime WHERE slug = ?",
            (slug,),
        ).fetchone()
        last_played = int(current_last_played[0]) if current_last_played else 0
        if episode_count == 0 or last_played > episode_count:
            last_played = 0

        connection.execute(
            """
            UPDATE anime
            SET episode_count = ?,
                episode_root_domain = ?,
                episode_route = ?,
                episode_query_prefix = ?,
                episode_start_number = ?,
                episode_other = ?,
                playback_mode = ?,
                local_media_dir = ?,
                last_played_episode = ?
            WHERE slug = ?
            """,
            (
                episode_count,
                episode_root_domain,
                episode_route,
                episode_query_prefix,
                episode_start_number,
                episode_other,
                playback_mode,
                local_media_dir,
                last_played,
                slug,
            ),
        )
        connection.commit()
    load_catalog.cache_clear()


def record_last_played_episode(slug: str, episode_number: int) -> None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "UPDATE anime SET last_played_episode = ? WHERE slug = ?",
            (episode_number, slug),
        )
        connection.commit()
    load_catalog.cache_clear()


def load_episode_progress(slug: str) -> dict[int, dict[str, float | bool]]:
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT episode_number, position_seconds, duration_seconds, completed
            FROM episode_playback_progress
            WHERE slug = ?
            """,
            (slug,),
        ).fetchall()

    return {
        int(row["episode_number"]): {
            "position_seconds": float(row["position_seconds"]),
            "duration_seconds": float(row["duration_seconds"]),
            "completed": bool(row["completed"]),
        }
        for row in rows
    }


def latest_progress_episode(slug: str) -> int:
    with sqlite3.connect(DB_PATH) as connection:
        row = connection.execute(
            """
            SELECT episode_number
            FROM episode_playback_progress
            WHERE slug = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (slug,),
        ).fetchone()
    return int(row[0]) if row else 0


def load_playback_activity() -> dict[str, float]:
    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(
            "SELECT slug, qualified_played_at FROM anime_playback_activity"
        ).fetchall()
    return {str(row[0]): float(row[1]) for row in rows}


def record_playback_activity(slug: str) -> None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            INSERT INTO anime_playback_activity (slug, qualified_played_at)
            VALUES (?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                qualified_played_at = excluded.qualified_played_at
            """,
            (slug, time.time()),
        )
        connection.commit()


def save_episode_progress(
    slug: str,
    episode_number: int,
    position_seconds: float,
    duration_seconds: float,
    completed: bool,
) -> None:
    position_seconds = max(0.0, position_seconds)
    duration_seconds = max(0.0, duration_seconds)
    if duration_seconds > 0:
        position_seconds = min(position_seconds, duration_seconds)

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            INSERT INTO episode_playback_progress (
                slug,
                episode_number,
                position_seconds,
                duration_seconds,
                completed,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug, episode_number) DO UPDATE SET
                position_seconds = excluded.position_seconds,
                duration_seconds = excluded.duration_seconds,
                completed = excluded.completed,
                updated_at = excluded.updated_at
            """,
            (
                slug,
                episode_number,
                position_seconds,
                duration_seconds,
                1 if completed else 0,
                time.time(),
            ),
        )
        connection.execute(
            "UPDATE anime SET last_played_episode = ? WHERE slug = ?",
            (episode_number, slug),
        )
        connection.commit()
    load_catalog.cache_clear()
