from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .config import TEMPLATE_DIR
from .media import list_video_files
from .repository import load_episode_progress


@lru_cache(maxsize=None)
def load_template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def render_template(name: str, context: dict[str, str]) -> str:
    output = load_template(name)
    for key, value in context.items():
        output = output.replace(f"{{{{{key}}}}}", value)
    return output


def asset_url(path: str) -> str:
    return "/" + quote(path.replace("\\", "/"), safe="/")


def local_placeholder_url(title: str) -> str:
    initial = html.escape(title.strip()[:1] or "A")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 720">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#b4efe2"/><stop offset="1" stop-color="#9cceff"/>'
        '</linearGradient></defs><rect width="480" height="720" fill="url(#g)"/>'
        '<circle cx="120" cy="128" r="86" fill="rgba(255,255,255,.42)"/>'
        f'<text x="240" y="390" text-anchor="middle" font-family="sans-serif" font-size="132" font-weight="800" fill="#35685d">{initial}</text>'
        '</svg>'
    )
    return "data:image/svg+xml," + quote(svg, safe="/:;,+='#%")


def render_card(anime: dict[str, Any]) -> str:
    title = html.escape(anime["title"])
    subtitle = html.escape(anime["subtitle"])
    release_info = html.escape(anime["release_info"])
    poster_path = str(anime.get("poster_path", "") or "")
    still_path = str(anime.get("still_path", "") or "")
    detail_url = f"/anime/{quote(anime['slug'])}"
    search_text = " ".join([anime["title"], anime["subtitle"], *anime["keywords"]]).lower()
    if poster_path:
        poster_markup = f'<img class="poster-card__image" src="{asset_url(poster_path)}" alt="{title} 海报" loading="lazy">'
    else:
        initial = html.escape(str(anime["title"]).strip()[:1] or "A")
        poster_markup = f'<div class="poster-card__image poster-card__image--local" aria-hidden="true"><span>{initial}</span></div>'
    glow_style = f"background-image: url('{asset_url(still_path)}');" if still_path else ""
    badge = '<span class="poster-card__badge">本地</span>' if anime.get("playback_mode") == "local" else ""
    return f"""
    <article class="poster-card" data-search="{html.escape(search_text)}">
      <a class="poster-card__link" href="{detail_url}" aria-label="查看 {title} 详情">
        <div class="poster-card__glow" style="{glow_style}"></div>
        {poster_markup}
        <div class="poster-card__meta">
          <p class="poster-card__release">{release_info}</p>
          <h2>{title}</h2>
          <p class="poster-card__subtitle">{subtitle}</p>
          {badge}
        </div>
      </a>
    </article>
    """.strip()


def render_anime_form_page(
    values: dict[str, str],
    error_message: str = "",
    mode: str = "create",
) -> str:
    is_edit = mode == "edit"
    context = {
        "ERROR_BANNER": (
            f'<p class="editor-error">{html.escape(error_message)}</p>'
            if error_message
            else ""
        ),
        "FORM_ACTION": values.get("form_action", "/anime/create"),
        "FORM_EYEBROW": "EDIT ANIME" if is_edit else "NEW ANIME",
        "FORM_PANEL_EYEBROW": "Edit Entry" if is_edit else "Create Entry",
        "FORM_TITLE": "编辑番剧" if is_edit else "新增番剧",
        "FORM_HINT": (
            "修改基础信息、海报剧照、播放地址和剧集配置。slug 会保持不变。"
            if is_edit
            else "海报和剧照可以手填项目内路径或直接上传；M3U8 资源可不提供图片。"
        ),
        "SLUG_READONLY": "readonly" if is_edit else "",
        "SUBMIT_LABEL": "保存修改" if is_edit else "创建番剧",
        "SLUG": html.escape(values.get("slug", ""), quote=True),
        "TITLE": html.escape(values.get("title", ""), quote=True),
        "SUBTITLE": html.escape(values.get("subtitle", ""), quote=True),
        "RELEASE_INFO": html.escape(values.get("release_info", ""), quote=True),
        "STUDIO": html.escape(values.get("studio", ""), quote=True),
        "POSTER_PATH": html.escape(values.get("poster_path", ""), quote=True),
        "STILL_PATH": html.escape(values.get("still_path", ""), quote=True),
        "PLAYBACK_URL": html.escape(values.get("playback_url", ""), quote=True),
        "RESOURCE_LINK_CHECKED": (
            "checked" if values.get("resource_type", "link") == "link" else ""
        ),
        "RESOURCE_PLAYLIST_CHECKED": (
            "checked" if values.get("resource_type", "link") == "playlist" else ""
        ),
        "RESOURCE_URL_LIST_CHECKED": (
            "checked" if values.get("resource_type", "link") == "url_list" else ""
        ),
        "PLAYLIST_FILE_STATUS": html.escape(
            values.get("playlist_name", "") or "未选择文件"
        ),
        "URL_LIST_TEXT": html.escape(values.get("url_list_text", "")),
        "PLAYBACK_MODE_ONLINE_CHECKED": (
            "checked" if values.get("playback_mode", "online") != "local" else ""
        ),
        "PLAYBACK_MODE_LOCAL_CHECKED": (
            "checked" if values.get("playback_mode", "online") == "local" else ""
        ),
        "LOCAL_MEDIA_DIR": html.escape(values.get("local_media_dir", ""), quote=True),
        "SYNOPSIS": html.escape(values.get("synopsis", "")),
        "CAST_TEXT": html.escape(values.get("cast_text", "")),
        "KEYWORD_TEXT": html.escape(values.get("keyword_text", "")),
        "SOURCE_TEXT": html.escape(values.get("source_text", "")),
        "EPISODE_COUNT": html.escape(values.get("episode_count", "0"), quote=True),
        "EPISODE_ROOT_DOMAIN": html.escape(
            values.get("episode_root_domain", ""), quote=True
        ),
        "EPISODE_ROUTE": html.escape(values.get("episode_route", ""), quote=True),
        "EPISODE_QUERY_PREFIX": html.escape(
            values.get("episode_query_prefix", ""), quote=True
        ),
        "EPISODE_START_NUMBER": html.escape(
            values.get("episode_start_number", "1"), quote=True
        ),
        "PLAYLIST_EPISODE_OFFSET": html.escape(
            values.get("playlist_episode_offset", "0"), quote=True
        ),
        "EPISODE_OTHER": html.escape(values.get("episode_other", ""), quote=True),
    }
    return render_template("anime_form.html", context)


def render_chip_list(items: list[str], variant: str) -> str:
    return "\n".join(
        f'<li class="{variant}-chip">{html.escape(item)}</li>' for item in items
    )


def render_source_list(items: list[dict[str, str]]) -> str:
    return "\n".join(
        (
            '<li><a href="{url}" target="_blank" rel="noreferrer">'
            "{label}</a></li>"
        ).format(url=html.escape(item["url"]), label=html.escape(item["label"]))
        for item in items
    )


def render_playback_section(anime: dict[str, Any]) -> str:
    if anime.get("playback_mode") == "local":
        local_dir = html.escape(str(anime.get("local_media_dir", "") or ""))
        return f'<section class="playback-card playback-card--local"><p>本地媒体库：{local_dir}</p></section>'
    if anime.get("resource_type") == "playlist":
        playlist_name = html.escape(str(anime.get("playlist_name", "") or "M3U8 播放列表"))
        episode_count = len(anime.get("playlist_episodes", []))
        return (
            '<section class="playback-card playback-card--playlist">'
            f'<p>资源：{playlist_name} · 已解析 {episode_count} 集</p>'
            "</section>"
        )
    slug = quote(str(anime["slug"]))
    playback_url = str(anime.get("playback_url", "") or "")
    playback_open_url = f"/anime/{slug}/playback"
    return f"""
    <section class="playback-card">
      <form class="playback-form" method="post" action="/anime/{slug}/playback-url" data-playback-form data-playback-open-url="{html.escape(playback_open_url, quote=True)}">
        <input
          class="playback-form__input"
          data-playback-input
          name="playback_url"
          type="url"
          inputmode="url"
          aria-label="番剧播放地址"
          placeholder="请输入播放地址"
          value="{html.escape(playback_url, quote=True)}"
          readonly
        >
        <div class="playback-form__dock" data-playback-dock>
          <div class="playback-form__actions">
            <button class="playback-form__button playback-form__button--toggle" type="button" data-edit-toggle aria-pressed="false">编辑地址</button>
            <button class="playback-form__button playback-form__button--save" type="submit" data-save-button disabled>保存地址</button>
          </div>
        </div>
      </form>
    </section>
    """.strip()


def episode_url_components(anime: dict[str, Any]) -> dict[str, str]:
    return {
        "root_domain": str(anime.get("episode_root_domain", "") or "").strip(),
        "route": str(anime.get("episode_route", "") or "").strip(),
        "query_prefix": str(anime.get("episode_query_prefix", "") or "").strip(),
        "other": str(anime.get("episode_other", "") or "").strip(),
    }


def episode_start_number(anime: dict[str, Any]) -> int:
    raw_value = anime.get("episode_start_number", 1)
    if raw_value in (None, ""):
        return 1
    return int(raw_value)


def playlist_episode_offset(anime: dict[str, Any]) -> int:
    try:
        return max(0, int(anime.get("playlist_episode_offset", 0) or 0))
    except (TypeError, ValueError):
        return 0


def display_episode_number(anime: dict[str, Any], episode_number: int) -> int:
    if anime.get("resource_type") == "playlist":
        return episode_number + playlist_episode_offset(anime)
    return episode_number


def compose_episode_url(anime: dict[str, Any], episode_number: int) -> str:
    if anime.get("resource_type") == "playlist":
        episodes = anime.get("playlist_episodes", [])
        if 0 < episode_number <= len(episodes):
            return str(episodes[episode_number - 1].get("url", "") or "")
        return ""
    components = episode_url_components(anime)
    root_domain = components["root_domain"].rstrip("/")
    route = components["route"]
    start_number = episode_start_number(anime)
    mapped_episode_number = start_number + episode_number - 1
    if route and not route.startswith("/"):
        route = "/" + route
    return f"{root_domain}{route}{components['query_prefix']}{mapped_episode_number}{components['other']}"


def playback_mode(anime: dict[str, Any]) -> str:
    return "local" if anime.get("playback_mode") == "local" else "online"


def format_progress_time(seconds: float) -> str:
    if seconds <= 0:
        return "00:00"
    whole_seconds = int(seconds)
    hours = whole_seconds // 3600
    minutes = (whole_seconds % 3600) // 60
    secs = whole_seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


CHINESE_NUMERAL_VALUES = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def parse_season_number(raw_value: str) -> int | None:
    value = raw_value.strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    if "十" in value:
        left, _, right = value.partition("十")
        tens = CHINESE_NUMERAL_VALUES.get(left, 1) if left else 1
        ones = CHINESE_NUMERAL_VALUES.get(right, 0) if right else 0
        return tens * 10 + ones
    if len(value) == 1:
        return CHINESE_NUMERAL_VALUES.get(value)
    return None


def local_group_label(raw_name: str) -> str:
    cleaned = re.sub(r"【.*?】|\[.*?\]", "", raw_name).strip()
    compact = re.sub(r"\s+", " ", cleaned)
    lower = compact.lower()
    if "剧场版" in compact or "movie" in lower:
        return "剧场版"
    if "狂三外传" in compact:
        return "狂三外传"
    if "oad" in lower:
        return "OAD"
    if "ova" in lower:
        return "OVA"
    if lower in {"special", "specials"} or "specials" in lower:
        return "特别篇"

    season_match = re.search(r"season\s*0*(\d+)", lower)
    if season_match:
        season_number = int(season_match.group(1))
        return "特别篇" if season_number == 0 else f"第 {season_number} 季"

    chinese_match = re.search(r"第\s*([0-9一二两三四五六七八九十〇零]+)\s*季", compact)
    if chinese_match:
        season_number = parse_season_number(chinese_match.group(1))
        if season_number is not None:
            return f"第 {season_number} 季"

    return compact or "剧集"


def local_episode_group_for_file(file_path: Path, base_dir: Path) -> str:
    try:
        relative = file_path.relative_to(base_dir)
    except ValueError:
        return "剧集"
    if len(relative.parts) <= 1:
        return "剧集"
    return local_group_label(relative.parts[0])


def local_group_sort_key(label: str) -> tuple[int, int, str]:
    season_match = re.fullmatch(r"第 (\d+) 季", label)
    if season_match:
        return (0, int(season_match.group(1)), label)
    special_order = {"特别篇": 0, "OAD": 1, "OVA": 2, "狂三外传": 3}
    if label in special_order:
        return (1, special_order[label], label)
    if label == "剧场版":
        return (2, 0, label)
    return (3, 0, label)


def clean_local_episode_text(raw_text: str) -> str:
    fallback = raw_text.strip()
    bracket_parts = re.findall(r"\[([^\]]+)\]", fallback)
    cleaned = re.sub(r"【.*?】|\[.*?\]", " ", fallback)
    cleaned = re.sub(
        r"\([^)]*(?:1080|720|2160|x264|x265|hevc|aac|flac|bdrip|web|baha|bilibili|chs|cht)[^)]*\)",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:bd|bdrip|web-dl|webrip|hevc|x264|x265|aac|flac|dts-hd|ma|10bit|8bit|1080p|720p|2160p|mkv|mp4)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b\d{3,4}x\d{3,4}\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\[\]]", " ", cleaned)
    cleaned = re.sub(r"[._]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    if cleaned:
        return cleaned

    useful_parts = []
    for part in bracket_parts:
        compact = re.sub(r"[._]+", " ", part).strip()
        lower = compact.lower()
        if re.search(r"raws?$|sub$|subgroup|字幕组|1080|720|2160|x264|x265|hevc|aac|flac|bdrip|web|chs|cht|gb|10bit|8bit", lower):
            continue
        useful_parts.append(compact)
    return " ".join(useful_parts) or fallback


def local_episode_display_title(file_path: Path, base_dir: Path, group_label: str) -> str:
    try:
        relative = file_path.relative_to(base_dir)
    except ValueError:
        return clean_local_episode_text(file_path.stem)
    if group_label == "剧场版" and len(relative.parts) > 2:
        return clean_local_episode_text(relative.parts[-2])
    return clean_local_episode_text(file_path.stem)


def local_episode_source_label(file_path: Path, base_dir: Path, group_label: str) -> str:
    try:
        relative = file_path.relative_to(base_dir)
    except ValueError:
        return ""
    if len(relative.parts) <= 2:
        return ""
    parent_parts = list(relative.parts[1:-1])
    if group_label == "剧场版" and parent_parts:
        parent_parts = parent_parts[:-1]
    labels = [clean_local_episode_text(part) for part in parent_parts]
    labels = [label for label in labels if label and label != group_label]
    return " / ".join(labels)


def render_episode_section(anime: dict[str, Any]) -> str:
    mode = playback_mode(anime)
    playlist_episodes = (
        anime.get("playlist_episodes", [])
        if anime.get("resource_type") == "playlist"
        else []
    )
    local_files = list_video_files(str(anime.get("local_media_dir", "") or "")) if mode == "local" else []
    count = (
        len(local_files)
        if mode == "local"
        else len(playlist_episodes) if playlist_episodes else int(anime.get("episode_count") or 0)
    )
    last_played = int(anime.get("last_played_episode") or 0)
    if last_played > count:
        last_played = 0

    selected_title = f"第 {last_played} 集" if last_played > 0 else "选择剧集开始播放"
    episodes_container_class = "episodes-grid"
    progress_by_episode = load_episode_progress(str(anime["slug"])) if mode == "local" else {}
    if count <= 0:
        empty_text = "本地目录中没有找到支持的视频文件" if mode == "local" else "尚未配置剧集"
        episodes = f'<p class="episodes-empty">{empty_text}</p>'
    elif mode == "local":
        episodes_container_class = "episode-seasons"
        base_dir = Path(str(anime.get("local_media_dir", "") or "")).expanduser().resolve()
        grouped_files: dict[str, list[tuple[int, Path]]] = {}
        for global_episode_number, file_path in enumerate(local_files, 1):
            group_label = local_episode_group_for_file(file_path, base_dir)
            grouped_files.setdefault(group_label, []).append((global_episode_number, file_path))

        groups: list[dict[str, Any]] = []
        for group_label, group_files in sorted(grouped_files.items(), key=lambda item: local_group_sort_key(item[0])):
            group: dict[str, Any] = {"label": group_label, "items": []}
            source_episode_counts: dict[str, int] = {}
            for _, (global_episode_number, file_path) in enumerate(group_files, 1):
                active = " episode-card--active" if global_episode_number == last_played else ""
                episode_name = local_episode_display_title(file_path, base_dir, group_label)
                source_label = local_episode_source_label(file_path, base_dir, group_label)
                source_key = source_label or "__default__"
                source_episode_counts[source_key] = source_episode_counts.get(source_key, 0) + 1
                local_episode_number = source_episode_counts[source_key]
                episode_label = f"第 {local_episode_number} 集"
                episode_title = f"{group_label} · {episode_label} · {episode_name}"
                if global_episode_number == last_played:
                    selected_title = episode_title
                source_markup = (
                    f'<span class="episode-card__source">{html.escape(source_label)}</span>'
                    if source_label
                    else ""
                )
                progress = progress_by_episode.get(global_episode_number, {})
                position_seconds = float(progress.get("position_seconds", 0.0))
                duration_seconds = float(progress.get("duration_seconds", 0.0))
                completed = bool(progress.get("completed", False))
                if completed:
                    progress_text = "已看完"
                elif position_seconds > 0:
                    progress_text = f"看到 {format_progress_time(position_seconds)}"
                else:
                    progress_text = ""
                progress_markup = (
                    f'<span class="episode-card__progress" data-progress-label>{html.escape(progress_text)}</span>'
                    if progress_text
                    else '<span class="episode-card__progress" data-progress-label hidden></span>'
                )
                try:
                    relative_title = file_path.relative_to(base_dir).as_posix()
                except ValueError:
                    relative_title = file_path.name
                group["items"].append(
                    """
                    <a class="episode-card{active}" href="{episode_url}" title="{relative_title}" data-local-episode data-episode-number="{episode}" data-episode-title="{title}" data-progress-position="{position}" data-progress-duration="{duration}" data-progress-completed="{completed}">
                      <span class="episode-card__roman">{local_episode}</span>
                      <span class="episode-card__label">{label}</span>
                      <span class="episode-card__title">{episode_name}</span>
                      {source_markup}
                      {progress_markup}
                    </a>
                    """.strip().format(
                        active=active,
                        episode_url=html.escape(
                            f"/anime/{quote(str(anime['slug']))}/local-episode/{global_episode_number}",
                            quote=True,
                        ),
                        episode=global_episode_number,
                        local_episode=local_episode_number,
                        relative_title=html.escape(relative_title, quote=True),
                        title=html.escape(episode_title, quote=True),
                        label=html.escape(episode_label),
                        episode_name=html.escape(episode_name),
                        source_markup=source_markup,
                        progress_markup=progress_markup,
                        position=html.escape(f"{position_seconds:.3f}", quote=True),
                        duration=html.escape(f"{duration_seconds:.3f}", quote=True),
                        completed="1" if completed else "0",
                    )
                )
            groups.append(group)

        season_blocks = []
        for group in groups:
            items = "\n".join(group["items"])
            count_label = len(group["items"])
            season_blocks.append(
                f"""
                <section class="episode-season">
                  <div class="episode-season__head">
                    <h3>{html.escape(group['label'])}</h3>
                    <span>{count_label} 个视频</span>
                  </div>
                  <div class="episodes-grid">
                    {items}
                  </div>
                </section>
                """.strip()
            )
        episodes = "\n".join(season_blocks)
    else:
        episode_items = []
        for episode_number in range(1, count + 1):
            active = " episode-card--active" if episode_number == last_played else ""
            episode_title = (
                str(playlist_episodes[episode_number - 1].get("title", "") or "")
                if playlist_episodes
                else ""
            )
            title_markup = (
                f'<span class="episode-card__title">{html.escape(episode_title)}</span>'
                if episode_title
                else ""
            )
            episode_items.append(
                """
                <a class="episode-card{active}" href="/anime/{slug}/episode/{episode}" target="_blank" rel="noreferrer noopener" title="{title}">
                  <span class="episode-card__roman">{display_episode}</span>
                  <span class="episode-card__label">第 {display_episode} 集</span>
                  {title_markup}
                </a>
                """.strip().format(
                    active=active,
                    slug=quote(anime["slug"]),
                    episode=episode_number,
                    display_episode=display_episode_number(anime, episode_number),
                    title=html.escape(episode_title, quote=True),
                    title_markup=title_markup,
                )
            )
        episodes = "\n".join(episode_items)

    local_player = ""
    if mode == "local":
        has_initial = 0 < last_played <= count
        initial_src = (
            f"/anime/{quote(str(anime['slug']))}/local-episode/{last_played}"
            if has_initial
            else ""
        )
        initial_mpv_url = (
            f"/anime/{quote(str(anime['slug']))}/mpv-playlist/{last_played}"
            if has_initial
            else "#"
        )
        initial_title = selected_title if has_initial else "选择剧集开始播放"
        hidden_attr = "" if has_initial else " hidden"
        mpv_hidden_attr = "" if has_initial else " hidden"
        local_player = f"""
        <div class="local-player" data-local-player data-progress-url="/anime/{quote(anime['slug'])}/episodes/progress"{hidden_attr}>
          <div class="local-player__head">
            <div>
              <p class="local-player__eyebrow">Local Player</p>
              <h3 data-local-player-title>{html.escape(initial_title)}</h3>
            </div>
            <div class="local-player__head-actions">
              <a class="local-player__mpv-link" href="{html.escape(initial_mpv_url, quote=True)}" data-mpv-link{mpv_hidden_attr}>MPV</a>
              <span class="local-player__badge">本地播放</span>
            </div>
          </div>
          <div class="local-player__stage" data-local-player-stage tabindex="0">
            <video class="local-player__video" data-local-video preload="metadata" src="{html.escape(initial_src, quote=True)}"></video>
            <button class="local-player__center-play" type="button" data-player-toggle aria-label="播放">▶</button>
            <div class="local-player__controls" data-player-controls>
              <label class="local-player__timeline" aria-label="播放进度">
                <input data-player-seek type="range" min="0" max="1000" value="0" step="1">
              </label>
              <div class="local-player__control-row">
                <div class="local-player__control-group">
                  <button class="local-player__icon-button" type="button" data-player-prev aria-label="上一集">上一集</button>
                  <button class="local-player__play-button" type="button" data-player-toggle aria-label="播放">▶</button>
                  <button class="local-player__icon-button" type="button" data-player-next aria-label="下一集">下一集</button>
                  <span class="local-player__time"><span data-player-current>00:00</span> / <span data-player-duration>00:00</span></span>
                </div>
                <div class="local-player__control-group local-player__control-group--right">
                  <label class="local-player__volume" aria-label="音量">
                    <span data-player-volume-icon>音量</span>
                    <input data-player-volume type="range" min="0" max="1" value="1" step="0.01">
                  </label>
                  <select class="local-player__speed" data-player-speed aria-label="播放速度">
                    <option value="0.75">0.75x</option>
                    <option value="1" selected>1.0x</option>
                    <option value="1.25">1.25x</option>
                    <option value="1.5">1.5x</option>
                    <option value="2">2.0x</option>
                  </select>
                  <button class="local-player__icon-button" type="button" data-player-fullscreen aria-label="全屏">全屏</button>
                </div>
              </div>
            </div>
          </div>
        </div>
        """.strip()

    last_label = str(display_episode_number(anime, last_played)) if last_played > 0 else "未播放"
    episode_count_value = str(count) if count > 0 else "0"
    start_number_value = str(episode_start_number(anime))
    playlist_offset_value = str(playlist_episode_offset(anime))
    components = episode_url_components(anime)
    online_checked = "selected" if mode == "online" else ""
    local_checked = "selected" if mode == "local" else ""
    local_media_dir = str(anime.get("local_media_dir", "") or "")
    is_playlist = anime.get("resource_type") == "playlist"
    config_button = "" if is_playlist else '<button class="episodes-panel__config-toggle" type="button" data-episodes-config-toggle aria-expanded="false">配置</button>'
    config_form = "" if is_playlist else f"""
      <form class="episodes-config" method="post" action="/anime/{quote(anime['slug'])}/episodes/config" data-episodes-config-form hidden>
        <div class="episodes-config__grid">
          <label class="episodes-config__field">
            <span>播放模式</span>
            <select name="playback_mode" data-playback-mode>
              <option value="online" {online_checked}>在线跳转</option>
              <option value="local" {local_checked}>本地页内播放</option>
            </select>
          </label>
          <label class="episodes-config__field" data-online-config>
            <span>总集数</span>
            <input name="episode_count" type="number" min="0" step="1" value="{html.escape(episode_count_value, quote=True)}">
          </label>
          <label class="episodes-config__field" data-online-config>
            <span>根域名</span>
            <input name="episode_root_domain" type="text" value="{html.escape(components['root_domain'], quote=True)}">
          </label>
          <label class="episodes-config__field" data-online-config>
            <span>路由</span>
            <input name="episode_route" type="text" value="{html.escape(components['route'], quote=True)}">
          </label>
          <label class="episodes-config__field" data-online-config>
            <span>查询参数前缀</span>
            <input name="episode_query_prefix" type="text" value="{html.escape(components['query_prefix'], quote=True)}">
          </label>
          <label class="episodes-config__field" data-online-config>
            <span>集数查询偏移</span>
            <input name="episode_start_number" type="number" step="1" value="{html.escape(start_number_value, quote=True)}">
          </label>
          <label class="episodes-config__field" data-online-config>
            <span>集数</span>
            <input type="text" value="自动生成" readonly>
          </label>
          <label class="episodes-config__field" data-online-config>
            <span>其他</span>
            <input name="episode_other" type="text" value="{html.escape(components['other'], quote=True)}">
          </label>
          <label class="episodes-config__field episodes-config__field--wide" data-local-config>
            <span>本地番剧目录</span>
            <input name="local_media_dir" type="text" value="{html.escape(local_media_dir, quote=True)}" placeholder="/mnt/GameDriver/MediaLib/Anime/番剧名">
          </label>
        </div>
        <div class="episodes-config__actions">
          <button class="episodes-config__save" type="submit">保存配置</button>
        </div>
      </form>
    """
    return f"""
    <section class="episodes-panel" data-episodes-panel>
      <div class="episodes-panel__head">
        <div class="episodes-panel__title">
          <p class="episodes-panel__eyebrow">Episodes</p>
          <h2>剧集</h2>
        </div>
        <div class="episodes-panel__status">
          <span class="episodes-panel__status-label">上一次播放</span>
          <span class="episodes-panel__status-value" data-last-played-value>{last_label}</span>
        </div>
        {config_button}
      </div>
      {config_form}
      {local_player}
      <div class="{episodes_container_class}">
        {episodes}
      </div>
    </section>
    """.strip()
