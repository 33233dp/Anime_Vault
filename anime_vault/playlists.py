from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit


MAX_PLAYLIST_SIZE = 2 * 1024 * 1024
URL_PATH_SAFE = "/%:@!$&'()*+,;=-._~"
URL_QUERY_SAFE = "/%?:@!$&'()*+,;=-._~"


def to_chinese_num(number: int) -> str:
    """Match urls_to_m3u8/convert_to_m3u8.py episode numbering."""
    if number < 1:
        return str(number)
    chinese = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
    if number < 10:
        return chinese[number]
    if number < 100:
        tens, ones = divmod(number, 10)
        result = "十" if tens == 1 else chinese[tens] + "十"
        return result + (chinese[ones] if ones else "")
    return str(number)


def convert_urls_to_m3u8(
    url_text: str, prefix: str = "", episode_offset: int = 0
) -> bytes:
    """Generate the same M3U8 payload as convert_to_m3u8.py."""
    try:
        episode_offset = max(0, int(episode_offset))
    except (TypeError, ValueError):
        episode_offset = 0
    urls = [line.strip() for line in url_text.splitlines() if line.strip()]
    if not urls:
        raise ValueError("未提供任何 URL，请每行填写一个播放地址。")
    lines = ["#EXTM3U"]
    for index, url in enumerate(urls, start=1):
        episode = to_chinese_num(index + episode_offset)
        title = f"{prefix}-第{episode}集" if prefix else f"第{episode}集"
        lines.extend([f"#EXTINF:-1,{title}", url])
    return ("\n".join(lines) + "\n").encode("utf-8")


def normalize_http_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            "M3U8 中的播放地址必须是完整的 HTTP 或 HTTPS 链接："
            f"{raw_url}"
        )
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            quote(parsed.path, safe=URL_PATH_SAFE),
            quote(parsed.query, safe=URL_QUERY_SAFE),
            quote(parsed.fragment, safe=URL_QUERY_SAFE),
        )
    )


def parse_m3u8_upload(filename: str, payload: bytes) -> list[dict[str, str]]:
    if Path(filename).suffix.lower() != ".m3u8":
        raise ValueError("请选择 .m3u8 格式的播放列表文件。")
    if not payload:
        raise ValueError("上传的 M3U8 文件为空，请重新选择。")
    if len(payload) > MAX_PLAYLIST_SIZE:
        raise ValueError("M3U8 文件不能超过 2 MB。")

    try:
        content = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("M3U8 文件必须使用 UTF-8 编码。") from exc

    lines = [line.strip() for line in content.splitlines()]
    if not lines or lines[0].upper() != "#EXTM3U":
        raise ValueError("文件不是有效的 M3U8 播放列表：缺少 #EXTM3U。")

    episodes: list[dict[str, str]] = []
    pending_title = ""
    for line in lines[1:]:
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            _, separator, title = line.partition(",")
            pending_title = title.strip() if separator else ""
            continue
        if line.startswith("#"):
            continue

        playback_url = normalize_http_url(line)
        episode_number = len(episodes) + 1
        episodes.append(
            {
                "title": pending_title or f"第 {episode_number} 集",
                "url": playback_url,
            }
        )
        pending_title = ""

    if not episodes:
        raise ValueError("M3U8 文件中没有找到可播放的 HTTP/HTTPS 地址。")
    return episodes
