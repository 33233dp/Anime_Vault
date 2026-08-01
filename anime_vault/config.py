from __future__ import annotations

from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
BASE_DIR = PACKAGE_DIR.parent
DB_PATH = BASE_DIR / "data" / "anime.db"
TEMPLATE_DIR = BASE_DIR / "templates"
POSTER_DIR = BASE_DIR / "poster"
STILLS_DIR = BASE_DIR / "Stills"

DEFAULT_MEDIA_LIBRARY_DIRS = (
    Path("/mnt/alist"),
)
VIDEO_SUFFIXES = {
    ".mp4",
    ".m4v",
    ".webm",
    ".mkv",
    ".mov",
    ".avi",
    ".flv",
}
VIDEO_MIME_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".flv": "video/x-flv",
}
