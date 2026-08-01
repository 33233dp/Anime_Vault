from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

from .config import VIDEO_MIME_TYPES, VIDEO_SUFFIXES
from .repository import load_media_library_paths


def _resolved_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for raw_root in load_media_library_paths():
        try:
            roots.append(Path(raw_root).resolve())
        except OSError:
            continue
    return tuple(roots)


def is_allowed_media_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return any(resolved == root or resolved.is_relative_to(root) for root in _resolved_roots())


def resolve_media_directory(raw_path: str) -> Path | None:
    if not raw_path.strip():
        return None
    try:
        directory = Path(raw_path).expanduser().resolve()
    except OSError:
        return None
    if not directory.is_dir() or not is_allowed_media_path(directory):
        return None
    return directory


def _sort_key(path: Path, base_dir: Path) -> str:
    return path.relative_to(base_dir).as_posix().lower()


def list_video_files(raw_directory: str) -> list[Path]:
    directory = resolve_media_directory(raw_directory)
    if directory is None:
        return []
    files = [
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    ]
    return sorted(files, key=lambda path: _sort_key(path, directory))


def episode_file_for_number(raw_directory: str, episode_number: int) -> Path | None:
    files = list_video_files(raw_directory)
    if episode_number <= 0 or episode_number > len(files):
        return None
    return files[episode_number - 1]


def video_mime_type(path: Path) -> str:
    return VIDEO_MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")


@lru_cache(maxsize=512)
def probe_video_stream(path_value: str) -> dict[str, str]:
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,profile,pix_fmt,width,height",
                "-of",
                "json",
                path_value,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if completed.returncode != 0:
        return {}
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    streams = payload.get("streams") or []
    if not streams:
        return {}
    stream = streams[0]
    return {str(key): str(value) for key, value in stream.items() if value is not None}


def needs_browser_compatible_stream(path: Path) -> bool:
    stream = probe_video_stream(path.as_posix())
    codec = stream.get("codec_name", "").lower()
    profile = stream.get("profile", "").lower()
    pixel_format = stream.get("pix_fmt", "").lower()
    suffix = path.suffix.lower()

    if codec in {"hevc", "h265", "av1", "vp9"}:
        return True
    if "10" in profile or "10" in pixel_format:
        return True
    if codec == "h264" and pixel_format not in {"", "yuv420p"}:
        return True
    return suffix not in {".mp4", ".m4v", ".webm"} and codec != "h264"

