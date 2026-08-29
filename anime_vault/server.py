from __future__ import annotations

import hashlib
import hmac
import html
import json
from email import policy
from email.parser import BytesParser
import os
import re
import time
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from .config import BASE_DIR, POSTER_DIR, STILLS_DIR
from .media import (
    episode_file_for_number,
    list_video_files,
    resolve_media_directory,
    video_mime_type,
)
from .playlists import convert_urls_to_m3u8, parse_m3u8_upload
from .renderers import (
    asset_url,
    compose_episode_url,
    display_episode_number,
    local_placeholder_url,
    render_anime_form_page,
    render_card,
    render_chip_list,
    render_episode_section,
    render_playback_section,
    render_source_list,
    render_template,
)
from .repository import (
    anime_exists,
    create_anime,
    delete_anime,
    get_anime,
    load_catalog,
    load_playback_activity,
    record_playback_activity,
    record_last_played_episode,
    load_privacy_settings,
    save_access_password,
    save_episode_progress,
    save_episode_config,
    save_playback_url,
    update_anime,
    verify_access_password,
)


ALLOWED_IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
    ".avif",
}
IMAGE_SUFFIX_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/svg+xml": ".svg",
    "image/avif": ".avif",
}
UPLOAD_TARGETS = {
    "poster_file": (POSTER_DIR, "poster"),
    "still_file": (STILLS_DIR, "still"),
}
AUTH_COOKIE_NAME = "anime_vault_session"
AUTH_SESSION_SECONDS = 12 * 60 * 60


class AnimeRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self) -> None:
        if self.handle_authentication_gate():
            return
        if self.handle_dynamic_route(include_body=True):
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        if self.handle_authentication_gate():
            return
        if self.handle_dynamic_route(include_body=False):
            return
        super().do_HEAD()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        route = unquote(parsed.path)
        if route == "/auth/unlock":
            self.unlock_site()
            return
        if route == "/auth/setup":
            self.setup_site_password()
            return
        if route == "/auth/logout":
            self.logout_site()
            return
        if self.handle_authentication_gate():
            return
        if route == "/anime/create":
            self.create_anime_entry()
            return
        if route.startswith("/anime/") and route.endswith("/delete"):
            slug = route.removeprefix("/anime/").removesuffix("/delete").strip("/")
            if slug:
                self.delete_anime_entry(slug)
                return
        if route.startswith("/anime/") and route.endswith("/edit"):
            slug = route.removeprefix("/anime/").removesuffix("/edit").strip("/")
            if slug:
                self.update_anime_entry(slug)
                return
        if route.startswith("/anime/") and route.endswith("/playback-url"):
            slug = route.removeprefix("/anime/").removesuffix("/playback-url").strip("/")
            if slug:
                self.update_playback_url(slug)
                return
        if route.startswith("/anime/") and route.endswith("/episodes/config"):
            slug = route.removeprefix("/anime/").removesuffix("/episodes/config").strip("/")
            if slug:
                self.update_episode_config(slug)
                return
        if route.startswith("/anime/") and route.endswith("/episodes/progress"):
            slug = route.removeprefix("/anime/").removesuffix("/episodes/progress").strip("/")
            if slug:
                self.update_episode_progress(slug)
                return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def handle_dynamic_route(self, include_body: bool) -> bool:
        parsed = urlparse(self.path)
        route = unquote(parsed.path)
        if route in {"/animeko/subscription", "/animeko/subscription.json"}:
            self.animeko_subscription(include_body)
            return True
        if route == "/animeko/search":
            self.animeko_search(include_body)
            return True
        if route.startswith("/animeko/anime/"):
            slug = route.removeprefix("/animeko/anime/").strip("/")
            if slug:
                self.animeko_detail(slug, include_body)
                return True
        if route == "/":
            self.render_home(include_body=include_body)
            return True
        if route in {"/auth", "/auth/setup"}:
            auth_mode = "unlock"
            if route == "/auth/setup" and (
                not self.password_is_configured() or self.has_valid_auth_session()
            ):
                auth_mode = "setup"
            self.render_auth_page(
                auth_mode,
                include_body=include_body,
            )
            return True
        if route == "/anime/new":
            self.render_anime_form(include_body=include_body)
            return True
        if route.startswith("/anime/"):
            inner_route = route.removeprefix("/anime/").strip("/")
            if inner_route.endswith("/edit"):
                slug = inner_route.removesuffix("/edit").strip("/")
                if slug:
                    self.render_anime_edit_form(slug, include_body=include_body)
                    return True
            if "/local-episode/" in inner_route:
                slug, episode_raw = inner_route.split("/local-episode/", 1)
                if slug and episode_raw.isdigit():
                    self.stream_local_episode(slug, int(episode_raw), include_body)
                    return True
            if "/mpv-playlist/" in inner_route:
                slug, episode_raw = inner_route.split("/mpv-playlist/", 1)
                if slug and episode_raw.isdigit():
                    self.serve_mpv_playlist(slug, int(episode_raw), include_body)
                    return True
            if inner_route.endswith("/playback") and include_body:
                slug = inner_route.removesuffix("/playback").strip("/")
                if slug:
                    self.play_online_entry(slug)
                    return True
            if "/episode/" in inner_route and include_body:
                slug, episode_raw = inner_route.split("/episode/", 1)
                if slug and episode_raw.isdigit():
                    self.play_episode(slug, int(episode_raw))
                    return True
            if inner_route:
                self.render_detail(inner_route, include_body=include_body)
                return True
        return False

    def animeko_url_token(self) -> str:
        token = parse_qs(urlparse(self.path).query).get("token", [""])[0].strip()
        return f"&token={quote(token)}" if token else ""

    def animeko_base_url(self) -> str:
        forwarded = self.headers.get("X-Forwarded-Proto", "http").split(",", 1)[0].strip()
        host = self.headers.get("Host", "127.0.0.1:8000")
        return f"{forwarded}://{host}".rstrip("/")

    def animeko_subscription_url(self) -> str:
        host = self.headers.get("Host", "127.0.0.1:8000")
        hostname = urlparse(f"//{host}").hostname or "127.0.0.1"
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        token = quote(os.environ.get("ANIMEKO_API_TOKEN", "").strip(), safe="")
        return f"http://{hostname}:8000/animeko/subscription?token={token}"

    def animeko_search(self, include_body: bool = True) -> None:
        if not include_body:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        query = parse_qs(urlparse(self.path).query).get("keyword", [""])[0].strip().casefold()
        token_suffix = self.animeko_url_token()
        results = []
        for anime in load_catalog():
            haystack = " ".join(
                [str(anime.get("title", "")), str(anime.get("subtitle", ""))]
                + [str(value) for value in anime.get("keywords", [])]
            ).casefold()
            if query and query not in haystack:
                continue
            slug = quote(str(anime["slug"]), safe="")
            results.append(
                {
                    "title": str(anime.get("title", anime["slug"])),
                    "name": str(anime.get("title", anime["slug"])),
                    "url": f"{self.animeko_base_url()}/animeko/anime/{slug}{('?token=' + quote(parse_qs(urlparse(self.path).query).get('token', [''])[0])) if token_suffix else ''}",
                }
            )
        self.respond_json(results)

    def animeko_subscription(self, include_body: bool = True) -> None:
        """Return an Animeko ExportedMediaSourceData subscription document."""
        if not include_body:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        parsed = urlparse(self.path)
        token = parse_qs(parsed.query).get("token", [""])[0].strip()
        token_query = f"?token={quote(token)}&keyword={{keyword}}" if token else "?keyword={{keyword}}"
        base = self.animeko_base_url()
        arguments = {
            "name": "Anime Vault",
            "description": "Anime Vault 本地番剧资源",
            "iconUrl": f"{base}/static/favicon.ico",
            "tier": 0,
            "channelTiers": {},
            "searchConfig": {
                "searchUrl": f"{base}/animeko/search{token_query}",
                "searchUseOnlyFirstWord": False,
                "searchRemoveSpecial": False,
                "searchUseSubjectNamesCount": 1,
                "rawBaseUrl": base,
                "subjectFormatId": "json-path-indexed",
                "selectorSubjectFormatJsonPathIndexed": {
                    "selectLinks": "$[*]['url','link']",
                    "selectNames": "$[*]['title','name']",
                    "preferShorterName": True,
                },
                "channelFormatId": "no-channel",
                "selectorChannelFormatNoChannel": {
                    "selectEpisodes": "a.animeko-episode",
                    "selectEpisodeLinks": "",
                    "matchEpisodeSortFromName": "第\\s*(?<ep>\\d+)\\s*[话集]",
                },
                "filterByEpisodeSort": True,
                "filterBySubjectName": True,
                "selectMedia": {"distinguishSubjectName": True, "distinguishChannelName": False},
                "matchVideo": {
                    "enableNestedUrl": True,
                    "matchNestedUrl": "^.+(m3u8|vip|xigua\\.php).+\\?",
                    "matchVideoUrl": "^http(s)?://.+",
                    "cookies": "",
                    "addHeadersToVideo": {"referer": "", "userAgent": ""},
                },
                "defaultResolution": "1080P",
                "defaultSubtitleLanguage": "ChineseSimplified",
            },
        }
        self.respond_json({
            "exportedMediaSourceDataList": {
                "mediaSources": [{"factoryId": "web-selector", "version": 2, "arguments": arguments}]
            }
        })

    def animeko_detail(self, slug: str, include_body: bool = True) -> None:
        anime = get_anime(slug)
        if anime is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Anime not found")
            return
        token_suffix = self.animeko_url_token()
        mode = str(anime.get("playback_mode", "online"))
        if mode == "local":
            count = len(list_video_files(str(anime.get("local_media_dir", ""))))
        elif anime.get("resource_type") == "playlist":
            count = len(anime.get("playlist_episodes", []))
        else:
            count = int(anime.get("episode_count") or 0)
        items = []
        for episode in range(1, count + 1):
            if mode == "local":
                href = f"{self.animeko_base_url()}/anime/{quote(slug, safe='')}/local-episode/{episode}{('?' + token_suffix.removeprefix('&')) if token_suffix else ''}"
            else:
                href = compose_episode_url(anime, episode)
                if not href:
                    continue
            title = ""
            if anime.get("resource_type") == "playlist":
                title = str(anime.get("playlist_episodes", [])[episode - 1].get("title", "") or "")
            # Keep the visible text limited to a canonical episode label. Animeko's
            # default greedy episode regex otherwise captures a later "集" in the
            # original M3U8 title (for example, "第 1 集 · ...第一集").
            label = f"第 {display_episode_number(anime, episode)} 集"
            title_attr = f' title="{html.escape(title, quote=True)}"' if title else ""
            items.append(
                f'<a class="animeko-episode" href="{html.escape(href, quote=True)}"{title_attr}>{label}</a>'
            )
        page = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{title}</title></head><body><main><h1>{title}</h1><div class="animeko-episodes">{episodes}</div></main></body></html>""".format(
            title=html.escape(str(anime.get("title", slug))), episodes="".join(items)
        )
        self.respond_html(page, include_body=include_body)

    def password_is_configured(self) -> bool:
        return load_privacy_settings() is not None

    def has_valid_auth_session(self) -> bool:
        settings = load_privacy_settings()
        if settings is None:
            return False

        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except (CookieError, ValueError):
            return False
        morsel = cookie.get(AUTH_COOKIE_NAME)
        if morsel is None:
            return False

        raw_value = morsel.value
        issued_at_raw, separator, signature = raw_value.partition(".")
        if not separator or not issued_at_raw.isdigit() or not signature:
            return False
        issued_at = int(issued_at_raw)
        now = int(time.time())
        if issued_at > now or now - issued_at > AUTH_SESSION_SECONDS:
            return False
        expected = hmac.new(
            bytes(settings["session_secret"]),
            issued_at_raw.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    def handle_authentication_gate(self) -> bool:
        route = unquote(urlparse(self.path).path)
        if route.startswith("/animeko/"):
            if self.animeko_authorized():
                return False
            self.respond_json({"error": "Animeko API authentication required"}, HTTPStatus.UNAUTHORIZED)
            return True
        if "/local-episode/" in route and self.animeko_token_present():
            if self.animeko_authorized():
                return False
            self.respond_json({"error": "Animeko API authentication required"}, HTTPStatus.UNAUTHORIZED)
            return True
        if route in {
            "/static/styles.css",
            "/static/app.js",
            "/auth",
            "/auth/setup",
        }:
            return False
        if not self.password_is_configured() or self.has_valid_auth_session():
            return False
        if route == "/":
            self.render_auth_page("unlock")
        else:
            self.redirect("/", HTTPStatus.FOUND)
        return True

    def animeko_token_present(self) -> bool:
        parsed = urlparse(self.path)
        return bool(
            parse_qs(parsed.query).get("token", [""])[0]
            or self.headers.get("X-Animeko-Token", "")
            or self.headers.get("Authorization", "")
        )

    def animeko_authorized(self) -> bool:
        """Allow Animeko access without a browser cookie when a token is configured."""
        if not self.password_is_configured() or self.has_valid_auth_session():
            return True
        configured = os.environ.get("ANIMEKO_API_TOKEN", "").strip()
        if not configured:
            return False
        parsed = urlparse(self.path)
        query_token = parse_qs(parsed.query).get("token", [""])[0]
        header_token = self.headers.get("X-Animeko-Token", "")
        authorization = self.headers.get("Authorization", "")
        bearer = authorization.removeprefix("Bearer ").strip()
        return any(
            hmac.compare_digest(candidate, configured)
            for candidate in (query_token, header_token, bearer)
            if candidate
        )

    def auth_cookie_value(self) -> str:
        settings = load_privacy_settings()
        if settings is None:
            return ""
        issued_at = str(int(time.time()))
        signature = hmac.new(
            bytes(settings["session_secret"]),
            issued_at.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        return f"{issued_at}.{signature}"

    def set_auth_cookie_header(self, value: str, max_age: int | None = None) -> str:
        attributes = [
            f"{AUTH_COOKIE_NAME}={value}",
            "Path=/",
            "HttpOnly",
            "SameSite=Strict",
        ]
        if max_age is not None:
            attributes.append(f"Max-Age={max_age}")
        return "; ".join(attributes)

    def unlock_site(self) -> None:
        if not self.password_is_configured():
            self.render_auth_page("setup")
            return
        form_data = self.read_form_data()
        password = form_data.get("password", [""])[0]
        if not verify_access_password(password):
            self.render_auth_page("unlock", "密码不正确，请重新输入。")
            return
        self.redirect(
            "/",
            HTTPStatus.SEE_OTHER,
            {"Set-Cookie": self.set_auth_cookie_header(self.auth_cookie_value())},
        )

    def setup_site_password(self) -> None:
        if self.password_is_configured() and not self.has_valid_auth_session():
            self.render_auth_page("unlock")
            return

        form_data = self.read_form_data()
        password = form_data.get("password", [""])[0]
        confirmation = form_data.get("password_confirmation", [""])[0]
        if len(password) < 6:
            self.render_auth_page("setup", "密码至少需要 6 个字符。")
            return
        if password != confirmation:
            self.render_auth_page("setup", "两次输入的密码不一致。")
            return

        save_access_password(password)
        self.redirect(
            "/",
            HTTPStatus.SEE_OTHER,
            {"Set-Cookie": self.set_auth_cookie_header(self.auth_cookie_value())},
        )

    def logout_site(self) -> None:
        self.redirect(
            "/",
            HTTPStatus.SEE_OTHER,
            {"Set-Cookie": self.set_auth_cookie_header("", max_age=0)},
        )

    def render_auth_page(
        self,
        mode: str,
        error_message: str = "",
        include_body: bool = True,
    ) -> None:
        is_setup = mode == "setup"
        page = render_template(
            "auth.html",
            {
                "AUTH_TITLE": "设置访问密码" if is_setup else "输入访问密码",
                "AUTH_EYEBROW": "FIRST-TIME PROTECTION" if is_setup else "PRIVATE LIBRARY",
                "AUTH_HINT": (
                    "设置后，之后访问网站需要输入密码。密码只以不可逆哈希形式保存在本机数据库中。"
                    if is_setup
                    else "这是一个私人番剧库，请输入访问密码继续。"
                ),
                "AUTH_FORM_ACTION": "/auth/setup" if is_setup else "/auth/unlock",
                "AUTH_SUBMIT_LABEL": "保存密码" if is_setup else "解锁馆藏",
                "AUTH_PASSWORD_AUTOCOMPLETE": (
                    "new-password" if is_setup else "current-password"
                ),
                "AUTH_CONFIRM_FIELD": (
                    """
                    <label class="auth-field">
                      <span>确认密码</span>
                      <input name="password_confirmation" type="password" required minlength="6" autocomplete="new-password">
                    </label>
                    """
                    if is_setup
                    else ""
                ),
                "ERROR_BANNER": (
                    f'<p class="auth-error" role="alert">{html.escape(error_message)}</p>'
                    if error_message
                    else ""
                ),
            },
        )
        self.respond_html(page, include_body=include_body)


    def is_catalog_entry_available(self, anime: dict[str, Any]) -> bool:
        if str(anime.get("playback_mode", "online")) != "local":
            return True
        return resolve_media_directory(str(anime.get("local_media_dir", ""))) is not None

    def combined_catalog(self) -> list[dict[str, Any]]:
        catalog = [
            anime for anime in load_catalog() if self.is_catalog_entry_available(anime)
        ]
        activity = load_playback_activity()
        return sorted(
            catalog,
            key=lambda anime: (
                -activity.get(str(anime["slug"]), 0.0),
                str(anime.get("title", "")).casefold(),
                str(anime["slug"]),
            ),
        )

    def get_catalog_entry(self, slug: str) -> dict[str, Any] | None:
        anime = get_anime(slug)
        return anime if anime is not None and self.is_catalog_entry_available(anime) else None

    def render_home(
        self,
        include_body: bool = True,
    ) -> None:
        catalog = self.combined_catalog()
        cards = "\n".join(render_card(anime) for anime in catalog)
        password_configured = self.password_is_configured()
        privacy_controls = f'''
          <div class="privacy-controls">
            <a class="privacy-link" href="/auth/setup">{'修改密码' if password_configured else '添加密码'}</a>
            {'<form method="post" action="/auth/logout"><button class="privacy-lock" type="submit">锁定</button></form>' if password_configured else ''}
          </div>
        '''
        page = render_template(
            "index.html",
            {
                "TOTAL_COUNT": str(len(catalog)),
                "POSTER_CARDS": cards,
                "PRIVACY_CONTROLS": privacy_controls,
                "ANIMEKO_SUBSCRIPTION_URL": html.escape(
                    self.animeko_subscription_url(), quote=True
                ),
            },
        )
        self.respond_html(page, include_body=include_body)

    def render_anime_form(
        self,
        include_body: bool = True,
        values: dict[str, str] | None = None,
        error_message: str = "",
        mode: str = "create",
    ) -> None:
        page = render_anime_form_page(values or {}, error_message, mode=mode)
        self.respond_html(page, include_body=include_body)

    def render_anime_edit_form(self, slug: str, include_body: bool = True) -> None:
        anime = get_anime(slug)
        if anime is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Anime not found")
            return

        self.render_anime_form(
            include_body=include_body,
            values=self.anime_to_form_values(anime),
            mode="edit",
        )

    def render_detail(self, slug: str, include_body: bool = True) -> None:
        anime = self.get_catalog_entry(slug)
        if anime is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Anime not found")
            return

        page = render_template(
            "detail.html",
            {
                "TITLE": html.escape(anime["title"]),
                "SUBTITLE": html.escape(anime["subtitle"]),
                "RELEASE_INFO": html.escape(anime["release_info"]),
                "STUDIO": html.escape(anime["studio"]),
                "SYNOPSIS": html.escape(anime["synopsis"]),
                "PLAYBACK_SECTION": render_playback_section(anime),
                "EPISODE_SECTION": render_episode_section(anime),
                "POSTER_URL": (
                    asset_url(anime["poster_path"])
                    if anime.get("poster_path")
                    else local_placeholder_url(str(anime["title"]))
                ),
                "BACKDROP_URL": asset_url(anime["still_path"]) if anime.get("still_path") else "",
                "CAST_ITEMS": render_chip_list(anime["cast"], "cast"),
                "KEYWORD_ITEMS": render_chip_list(anime["keywords"], "keyword"),
                "SOURCE_ITEMS": render_source_list(anime["sources"]),
                "BACK_LINK": "/",
                "EDIT_LINK": f"/anime/{quote(anime['slug'])}/edit",
                "DELETE_ACTION": f"/anime/{quote(anime['slug'])}/delete",
                "DELETE_TITLE": html.escape(str(anime.get("title", slug)), quote=True),
            },
        )
        self.respond_html(page, include_body=include_body)


    def delete_anime_entry(self, slug: str) -> None:
        if not delete_anime(slug):
            self.send_error(HTTPStatus.NOT_FOUND, "Anime not found")
            return
        self.redirect("/", HTTPStatus.SEE_OTHER)


    def update_playback_url(self, slug: str) -> None:
        if get_anime(slug) is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Anime not found")
            return

        form_data = self.read_form_data()
        playback_url = form_data.get("playback_url", [""])[0].strip()
        save_playback_url(slug, playback_url)
        self.redirect(f"/anime/{quote(slug)}", HTTPStatus.SEE_OTHER)

    def create_anime_entry(self) -> None:
        result = self.read_anime_form_record()
        values = result["values"]
        if result["error"]:
            self.render_anime_form(values=values, error_message=result["error"])
            return

        if anime_exists(values["slug"]):
            self.render_anime_form(
                values=values,
                error_message="该 slug 已存在，请换一个唯一标识。",
            )
            return

        create_anime(result["record"])
        self.redirect(f"/anime/{quote(values['slug'])}", HTTPStatus.SEE_OTHER)

    def update_anime_entry(self, slug: str) -> None:
        if get_anime(slug) is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Anime not found")
            return

        result = self.read_anime_form_record(existing_slug=slug)
        values = result["values"]
        if result["error"]:
            self.render_anime_form(
                values=values,
                error_message=result["error"],
                mode="edit",
            )
            return

        update_anime(slug, result["record"])
        self.redirect(f"/anime/{quote(slug)}", HTTPStatus.SEE_OTHER)

    def read_anime_form_record(self, existing_slug: str | None = None) -> dict[str, Any]:
        form_data, uploaded_files = self.read_request_data()
        existing_anime = get_anime(existing_slug) if existing_slug else None

        def field(name: str, default: str = "") -> str:
            return form_data.get(name, [default])[0].strip()

        slug = existing_slug or field("slug")
        values = {
            "slug": slug,
            "title": field("title"),
            "subtitle": field("subtitle"),
            "release_info": field("release_info"),
            "studio": field("studio"),
            "poster_path": field("poster_path"),
            "still_path": field("still_path"),
            "playback_url": field("playback_url"),
            "resource_type": self.normalize_resource_type(field("resource_type", "link")),
            "url_list_text": field("url_list_text"),
            "playlist_name": field("playlist_name"),
            "playback_mode": self.normalize_playback_mode(field("playback_mode", "online")),
            "local_media_dir": field("local_media_dir"),
            "synopsis": field("synopsis"),
            "cast_text": field("cast_text"),
            "keyword_text": field("keyword_text"),
            "source_text": field("source_text"),
            "episode_count": field("episode_count", "0"),
            "episode_root_domain": field("episode_root_domain"),
            "episode_route": field("episode_route"),
            "episode_query_prefix": field("episode_query_prefix"),
            "episode_start_number": field("episode_start_number", "1"),
            "playlist_episode_offset": field("playlist_episode_offset", "0"),
            "episode_other": field("episode_other"),
        }
        if existing_slug:
            values["form_action"] = f"/anime/{quote(existing_slug)}/edit"

        poster_upload = uploaded_files.get("poster_file")
        still_upload = uploaded_files.get("still_file")
        playlist_upload = uploaded_files.get("playlist_file")

        if not values["slug"] or not values["title"]:
            return {"values": values, "record": None, "error": "slug 和番剧名为必填项。"}

        requires_images = (
            values["playback_mode"] != "local"
            and values["resource_type"] == "link"
        )
        if requires_images:
            if not values["poster_path"] and not self.has_uploaded_file(poster_upload):
                return {
                    "values": values,
                    "record": None,
                    "error": "请填写海报路径，或直接上传海报图片。",
                }

            if not values["still_path"] and not self.has_uploaded_file(still_upload):
                return {
                    "values": values,
                    "record": None,
                    "error": "请填写详情页剧照/背景图路径，或直接上传剧照图片。",
                }

        if values["playback_mode"] == "local":
            if resolve_media_directory(values["local_media_dir"]) is None:
                return {
                    "values": values,
                    "record": None,
                    "error": "本地播放模式需要填写允许媒体库内存在的番剧目录。",
                }

        try:
            episode_count = max(0, int(values["episode_count"] or "0"))
        except ValueError:
            episode_count = 0
        try:
            episode_start_number = int(values["episode_start_number"] or "1")
        except ValueError:
            episode_start_number = 1
        try:
            playlist_episode_offset = max(0, int(values["playlist_episode_offset"] or "0"))
        except ValueError:
            playlist_episode_offset = 0

        playlist_episodes: list[dict[str, str]] = []
        playlist_name = ""
        if values["resource_type"] in {"playlist", "url_list"}:
            if self.has_uploaded_file(playlist_upload):
                try:
                    playlist_name = str(playlist_upload.get("filename", "") or "")
                    playlist_episodes = parse_m3u8_upload(
                        playlist_name,
                        playlist_upload.get("data", b""),
                    )
                except ValueError as exc:
                    return {"values": values, "record": None, "error": str(exc)}
            elif values["resource_type"] == "url_list":
                try:
                    playlist_name = f"{values['title'] or values['slug']}.m3u8"
                    generated_playlist = convert_urls_to_m3u8(
                        values["url_list_text"], values["title"], playlist_episode_offset
                    )
                    playlist_episodes = parse_m3u8_upload(playlist_name, generated_playlist)
                except ValueError as exc:
                    return {"values": values, "record": None, "error": str(exc)}
            elif existing_anime and existing_anime.get("resource_type") == "playlist":
                playlist_name = str(existing_anime.get("playlist_name", "") or "")
                playlist_episodes = list(existing_anime.get("playlist_episodes", []))
            else:
                return {
                    "values": values,
                    "record": None,
                    "error": "请选择要导入的 .m3u8 文件。",
                }
            episode_count = len(playlist_episodes)

        try:
            poster_path = self.resolve_image_path(
                slug=values["slug"],
                field_name="poster_file",
                uploaded_file=poster_upload,
                fallback_path=values["poster_path"],
            )
            still_path = self.resolve_image_path(
                slug=values["slug"],
                field_name="still_file",
                uploaded_file=still_upload,
                fallback_path=values["still_path"],
            )
        except ValueError as exc:
            return {"values": values, "record": None, "error": str(exc)}

        record = {
            "slug": values["slug"],
            "title": values["title"],
            "subtitle": values["subtitle"],
            "release_info": values["release_info"],
            "studio": values["studio"],
            "synopsis": values["synopsis"],
            "cast": self.parse_lines(values["cast_text"]),
            "keywords": self.parse_tag_lines(values["keyword_text"]),
            "poster_path": poster_path,
            "still_path": still_path,
            "sources": self.parse_sources(values["source_text"]),
            "playback_url": values["playback_url"],
            "playback_mode": values["playback_mode"],
            "local_media_dir": values["local_media_dir"],
            "episode_count": episode_count,
            "episode_root_domain": values["episode_root_domain"],
            "episode_route": values["episode_route"],
            "episode_query_prefix": values["episode_query_prefix"],
            "episode_start_number": episode_start_number,
            "playlist_episode_offset": playlist_episode_offset,
            "episode_other": values["episode_other"],
            "resource_type": "playlist" if values["resource_type"] in {"playlist", "url_list"} else values["resource_type"],
            "playlist_name": playlist_name or values["playlist_name"],
            "playlist_episodes": playlist_episodes,
            "last_played_episode": 0,
        }
        return {"values": values, "record": record, "error": ""}

    def anime_to_form_values(self, anime: dict[str, Any]) -> dict[str, str]:
        sources = [
            f"{source.get('label', '')} | {source.get('url', '')}"
            for source in anime.get("sources", [])
        ]
        slug = str(anime["slug"])
        return {
            "form_action": f"/anime/{quote(slug)}/edit",
            "slug": slug,
            "title": str(anime.get("title", "")),
            "subtitle": str(anime.get("subtitle", "")),
            "release_info": str(anime.get("release_info", "")),
            "studio": str(anime.get("studio", "")),
            "poster_path": str(anime.get("poster_path", "")),
            "still_path": str(anime.get("still_path", "")),
            "playback_url": str(anime.get("playback_url", "")),
            "resource_type": self.normalize_resource_type(str(anime.get("resource_type", "link"))),
            "playlist_name": str(anime.get("playlist_name", "")),
            "playback_mode": self.normalize_playback_mode(str(anime.get("playback_mode", "online"))),
            "local_media_dir": str(anime.get("local_media_dir", "")),
            "synopsis": str(anime.get("synopsis", "")),
            "cast_text": "\n".join(anime.get("cast", [])),
            "keyword_text": "\n".join(anime.get("keywords", [])),
            "source_text": "\n".join(sources),
            "episode_count": str(anime.get("episode_count") or 0),
            "episode_root_domain": str(anime.get("episode_root_domain", "")),
            "episode_route": str(anime.get("episode_route", "")),
            "episode_query_prefix": str(anime.get("episode_query_prefix", "")),
            "episode_start_number": str(anime.get("episode_start_number") or 1),
            "playlist_episode_offset": str(anime.get("playlist_episode_offset") or 0),
            "episode_other": str(anime.get("episode_other", "")),
        }

    def update_episode_config(self, slug: str) -> None:
        if get_anime(slug) is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Anime not found")
            return

        form_data = self.read_form_data()

        def field(name: str) -> str:
            return form_data.get(name, [""])[0].strip()

        playback_mode = self.normalize_playback_mode(field("playback_mode") or "online")
        local_media_dir = field("local_media_dir")
        if playback_mode == "local" and resolve_media_directory(local_media_dir) is None:
            self.send_error(
                HTTPStatus.BAD_REQUEST,
                "Local media directory must exist under the configured media libraries",
            )
            return

        try:
            episode_count = max(0, int(field("episode_count") or "0"))
        except ValueError:
            episode_count = 0
        try:
            episode_start_number = int(field("episode_start_number") or "1")
        except ValueError:
            episode_start_number = 1

        save_episode_config(
            slug=slug,
            episode_count=episode_count,
            episode_root_domain=field("episode_root_domain"),
            episode_route=field("episode_route"),
            episode_query_prefix=field("episode_query_prefix"),
            episode_start_number=episode_start_number,
            episode_other=field("episode_other"),
            playback_mode=playback_mode,
            local_media_dir=local_media_dir,
        )
        self.redirect(f"/anime/{quote(slug)}", HTTPStatus.SEE_OTHER)

    def update_episode_progress(self, slug: str) -> None:
        anime = self.get_catalog_entry(slug)
        if anime is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Anime not found")
            return
        if anime.get("playback_mode") != "local":
            self.send_error(HTTPStatus.BAD_REQUEST, "Episode progress is only available for local playback")
            return

        form_data = self.read_form_data()

        try:
            episode_number = int(form_data.get("episode_number", ["0"])[0])
        except ValueError:
            episode_number = 0
        if episode_number <= 0:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid episode number")
            return
        if episode_file_for_number(str(anime.get("local_media_dir", "") or ""), episode_number) is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Local episode not found")
            return

        try:
            position_seconds = float(form_data.get("position_seconds", ["0"])[0])
        except ValueError:
            position_seconds = 0.0
        try:
            duration_seconds = float(form_data.get("duration_seconds", ["0"])[0])
        except ValueError:
            duration_seconds = 0.0
        try:
            watched_seconds = float(form_data.get("watched_seconds", ["0"])[0])
        except ValueError:
            watched_seconds = 0.0
        completed = form_data.get("completed", ["0"])[0] == "1"

        save_episode_progress(
            slug=slug,
            episode_number=episode_number,
            position_seconds=position_seconds,
            duration_seconds=duration_seconds,
            completed=completed,
        )
        if watched_seconds >= 600:
            record_playback_activity(slug)
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def play_online_entry(self, slug: str) -> None:
        anime = get_anime(slug)
        if anime is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Anime not found")
            return
        if anime.get("playback_mode") == "local":
            self.send_error(HTTPStatus.NOT_FOUND, "Online playback is not configured")
            return

        playback_url = str(anime.get("playback_url", "") or "").strip()
        if not playback_url:
            self.send_error(HTTPStatus.BAD_REQUEST, "Playback URL is not configured")
            return

        record_playback_activity(slug)
        self.redirect(playback_url, HTTPStatus.FOUND)

    def play_episode(self, slug: str, episode_number: int) -> None:
        anime = get_anime(slug)
        if anime is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Anime not found")
            return

        episode_count = int(anime.get("episode_count") or 0)
        if episode_number <= 0 or episode_number > episode_count:
            self.send_error(HTTPStatus.NOT_FOUND, "Episode not found")
            return

        target_url = compose_episode_url(anime, episode_number)
        if not target_url.strip():
            self.send_error(HTTPStatus.BAD_REQUEST, "Episode URL is not configured")
            return

        record_last_played_episode(slug, episode_number)
        record_playback_activity(slug)

        # 对于 playlist 类型的资源，渲染内嵌播放器页面
        if anime.get("resource_type") == "playlist":
            title = html.escape(str(anime.get("title", slug)))
            ep_title = html.escape(
                f"第 {display_episode_number(anime, episode_number)} 集"
            )
            video_url = html.escape(target_url, quote=True)
            prev_link = ""
            next_link = ""
            if episode_number > 1:
                prev_link = f'<a href="/anime/{quote(slug)}/episode/{episode_number - 1}" class="nav-link">⬅ 上一集</a>'
            if episode_number < episode_count:
                next_link = f'<a href="/anime/{quote(slug)}/episode/{episode_number + 1}" class="nav-link">下一集 ➡</a>'

            page = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{ep_title} - {title} - Anime Vault</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      background: #000;
      color: #fff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    .player-container {{
      flex: 1;
      display: flex;
      flex-direction: column;
      max-width: 1200px;
      margin: 0 auto;
      width: 100%;
      padding: 12px;
    }}
    video {{
      width: 100%;
      max-height: 80vh;
      background: #000;
      border-radius: 8px;
      outline: none;
    }}
    .player-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 0;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .player-header h2 {{
      font-size: 18px;
      font-weight: 600;
    }}
    .nav-links {{
      display: flex;
      gap: 12px;
    }}
    .nav-link {{
      color: #8ab4f8;
      text-decoration: none;
      padding: 6px 16px;
      border: 1px solid #8ab4f8;
      border-radius: 6px;
      font-size: 14px;
      transition: background 0.2s;
    }}
    .nav-link:hover {{
      background: #8ab4f8;
      color: #000;
    }}
    .back-link {{
      color: #888;
      text-decoration: none;
      font-size: 14px;
      padding: 6px 0;
      display: inline-block;
    }}
    .back-link:hover {{ color: #fff; }}
    .episode-grid {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 12px 0;
    }}
    .ep-btn {{
      padding: 6px 14px;
      border: 1px solid #444;
      border-radius: 4px;
      background: transparent;
      color: #ccc;
      cursor: pointer;
      text-decoration: none;
      font-size: 13px;
      transition: all 0.2s;
    }}
    .ep-btn:hover, .ep-btn.active {{
      background: #8ab4f8;
      color: #000;
      border-color: #8ab4f8;
    }}
  </style>
</head>
<body>
  <div class="player-container">
    <a class="back-link" href="/anime/{quote(slug)}">← 返回详情页</a>
    <div class="player-header">
      <h2>{title} - {ep_title}</h2>
      <div class="nav-links">
        {prev_link}
        {next_link}
      </div>
    </div>
    <video id="video-player" controls autoplay preload="metadata">
      <source src="{video_url}" type="video/mp4">
      您的浏览器不支持视频播放。
    </video>
    <div class="episode-grid">
'''
            for i in range(1, episode_count + 1):
                active = "active" if i == episode_number else ""
                display_episode = display_episode_number(anime, i)
                page += '<a href="/anime/' + quote(slug) + '/episode/' + str(i) + '" class="ep-btn ' + active + '">' + str(display_episode) + '</a>'
            page += '''    </div>
  </div>
  <script>
    // 记住播放进度
    const video = document.getElementById('video-player');
    const storageKey = 'av_progress_''' + slug + '''_' + ''' + str(episode_number) + ''';
    const saved = localStorage.getItem(storageKey);
    if (saved) {{
      const pos = parseFloat(saved);
      if (pos > 0 && pos < video.duration) video.currentTime = pos;
    }}
    video.addEventListener('timeupdate', () => {{
      localStorage.setItem(storageKey, video.currentTime.toString());
    }});
    video.addEventListener('ended', () => {{
      localStorage.removeItem(storageKey);
    }});
  </script>
</body>
</html>'''
            self.respond_html(page)
            return

        self.redirect(target_url, HTTPStatus.FOUND)


    def stream_local_episode(
        self, slug: str, episode_number: int, include_body: bool = True
    ) -> None:
        anime = self.get_catalog_entry(slug)
        if anime is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Anime not found")
            return
        if anime.get("playback_mode") != "local":
            self.send_error(HTTPStatus.NOT_FOUND, "Local playback is not configured")
            return

        target_path = episode_file_for_number(
            str(anime.get("local_media_dir", "") or ""), episode_number
        )
        if target_path is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Local episode not found")
            return

        record_last_played_episode(slug, episode_number)
        self.respond_video_file(target_path, include_body=include_body)

    def serve_mpv_playlist(
        self, slug: str, episode_number: int, include_body: bool = True
    ) -> None:
        anime = self.get_catalog_entry(slug)
        if anime is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Anime not found")
            return
        if anime.get("playback_mode") != "local":
            self.send_error(HTTPStatus.NOT_FOUND, "Local playback is not configured")
            return

        target_path = episode_file_for_number(
            str(anime.get("local_media_dir", "") or ""), episode_number
        )
        if target_path is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Local episode not found")
            return

        record_last_played_episode(slug, episode_number)
        base_url = f"http://{self.headers.get('Host', '127.0.0.1:8000')}"
        media_url = f"{base_url}/anime/{quote(slug)}/local-episode/{episode_number}"
        title = f"{anime.get('title', slug)} - 第 {episode_number} 集"
        playlist = f"#EXTM3U\n#EXTINF:-1,{title}\n{media_url}\n"
        payload = playlist.encode("utf-8")
        filename = f"{self.slug_to_filename(slug)}-{episode_number:02d}.m3u"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "audio/x-mpegurl; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if include_body:
            self.wfile.write(payload)

    def respond_video_file(self, path: Path, include_body: bool = True) -> None:
        file_size = path.stat().st_size
        start = 0
        end = file_size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range", "")

        if range_header.startswith("bytes="):
            parsed_range = range_header.removeprefix("bytes=").split(",", 1)[0]
            raw_start, _, raw_end = parsed_range.partition("-")
            try:
                if raw_start:
                    start = int(raw_start)
                    end = int(raw_end) if raw_end else file_size - 1
                elif raw_end:
                    suffix_size = int(raw_end)
                    start = max(file_size - suffix_size, 0)
                if start < 0 or end < start or start >= file_size:
                    raise ValueError
                end = min(end, file_size - 1)
                status = HTTPStatus.PARTIAL_CONTENT
            except ValueError:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

        content_length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", video_mime_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "private, max-age=3600")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()
        if not include_body:
            return

        remaining = content_length
        with path.open("rb") as source:
            source.seek(start)
            while remaining > 0:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                remaining -= len(chunk)

    def normalize_playback_mode(self, value: str) -> str:
        return "local" if value == "local" else "online"

    def normalize_resource_type(self, value: str) -> str:
        if value in {"playlist", "url_list"}:
            return value
        return "link"

    def read_form_data(self) -> dict[str, list[str]]:
        form_data, _ = self.read_request_data()
        return form_data

    def read_request_data(
        self,
    ) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            return self.read_multipart_form_data()

        content_length = int(self.headers.get("Content-Length", "0") or 0)
        payload = self.rfile.read(content_length).decode("utf-8") if content_length else ""
        return parse_qs(payload, keep_blank_values=True), {}

    def read_multipart_form_data(
        self,
    ) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        payload = self.rfile.read(content_length) if content_length else b""
        # The stdlib email parser replaces the removed cgi.FieldStorage in Python 3.13.
        raw_message = (
            f"Content-Type: {self.headers.get('Content-Type', '')}\r\n"
            "MIME-Version: 1.0\r\n\r\n"
        ).encode("ascii", "replace") + payload
        form = BytesParser(policy=policy.default).parsebytes(raw_message)
        fields: dict[str, list[str]] = {}
        files: dict[str, dict[str, Any]] = {}
        if not form.is_multipart():
            return fields, files
        for item in form.iter_parts():
            disposition = item.get_content_disposition()
            name = item.get_param("name", header="content-disposition")
            if not name or disposition != "form-data":
                continue
            filename = item.get_filename()
            if filename:
                files[name] = {
                    "filename": filename,
                    "content_type": item.get_content_type() or "",
                    "data": item.get_payload(decode=True) or b"",
                }
                continue
            # Browsers commonly omit a charset on multipart text fields.  The
            # payload is still UTF-8, but email.message would otherwise decode
            # it as ASCII and replace every Chinese byte with U+FFFD.
            raw_value = item.get_payload(decode=True)
            if raw_value is not None:
                charset = item.get_content_charset() or "utf-8"
                try:
                    value = raw_value.decode(charset)
                except (LookupError, UnicodeDecodeError):
                    value = raw_value.decode("utf-8", errors="replace")
            else:
                value = item.get_content()
            fields.setdefault(name, []).append(str(value))
        return fields, files

    def has_uploaded_file(self, uploaded_file: dict[str, Any] | None) -> bool:
        if uploaded_file is None:
            return False
        return bool(uploaded_file.get("filename"))

    def resolve_image_path(
        self,
        slug: str,
        field_name: str,
        uploaded_file: dict[str, Any] | None,
        fallback_path: str,
    ) -> str:
        if not self.has_uploaded_file(uploaded_file):
            return fallback_path
        return self.save_uploaded_image(
            slug=slug,
            field_name=field_name,
            uploaded_file=uploaded_file,
        )

    def save_uploaded_image(
        self,
        slug: str,
        field_name: str,
        uploaded_file: dict[str, Any],
    ) -> str:
        filename = str(uploaded_file.get("filename", "") or "").strip()
        content_type = str(uploaded_file.get("content_type", "") or "").strip().lower()
        payload = uploaded_file.get("data", b"")
        if not isinstance(payload, bytes) or not payload:
            raise ValueError("上传的图片文件为空，请重新选择。")
        if content_type and not content_type.startswith("image/"):
            raise ValueError("只能上传图片文件，请重新选择。")

        suffix = Path(filename).suffix.lower()
        if not suffix:
            suffix = IMAGE_SUFFIX_BY_CONTENT_TYPE.get(content_type, "")
        if suffix not in ALLOWED_IMAGE_SUFFIXES:
            raise ValueError(
                "仅支持 JPG、JPEG、PNG、GIF、WEBP、BMP、SVG、AVIF 格式的图片上传。"
            )

        target_dir, target_suffix = UPLOAD_TARGETS[field_name]
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_slug = self.slug_to_filename(slug)
        target_path = target_dir / f"{safe_slug}-{target_suffix}{suffix}"
        target_path.write_bytes(payload)
        return target_path.relative_to(BASE_DIR).as_posix()

    def slug_to_filename(self, slug: str) -> str:
        normalized = re.sub(r"[^\w-]+", "-", slug.strip()).strip("-")
        return normalized or "anime"

    def parse_lines(self, raw_text: str) -> list[str]:
        return [line.strip() for line in raw_text.splitlines() if line.strip()]

    def parse_tag_lines(self, raw_text: str) -> list[str]:
        normalized = raw_text.replace("，", ",")
        items: list[str] = []
        for block in normalized.splitlines():
            for item in block.split(","):
                cleaned = item.strip()
                if cleaned:
                    items.append(cleaned)
        return items

    def parse_sources(self, raw_text: str) -> list[dict[str, str]]:
        sources: list[dict[str, str]] = []
        for line in raw_text.splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            if "|" in cleaned:
                label, url = cleaned.split("|", 1)
                sources.append({"label": label.strip(), "url": url.strip()})
            else:
                sources.append({"label": cleaned, "url": cleaned})
        return sources

    def redirect(
        self,
        location: str,
        status: HTTPStatus,
        headers: dict[str, str] | None = None,
    ) -> None:
        location = quote(location, safe="/:?#[]@!$&'()*+,;=%-._~")
        self.send_response(status)
        self.send_header("Location", location)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def respond_html(self, page: str, include_body: bool = True) -> None:
        payload = page.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if include_body:
            self.wfile.write(payload)

    def respond_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def create_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), AnimeRequestHandler)
