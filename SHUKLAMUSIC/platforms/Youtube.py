# ---------------------------------------------------------------
# 🔸 ShrutiMusic Api Youtube.py file.
# 🔹 Developed & Maintained by: Nand Yaduvanshi (https://github.com/NoxxOP)
# 📅 Copyright © 2025 – All Rights Reserved
# ❤️ Made with dedication and love by NoxxOP & itzshukla
# ---------------------------------------------------------------

import asyncio
import os
import random
import re
import time as _time
from typing import Union
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from py_yt import Playlist

DOWNLOAD_DIR = "downloads"
COOKIES_FILE = os.path.join(os.getcwd(), "SHUKLAMUSIC", "assets", "cookies.txt")

_SEARCH_CACHE: dict = {}
_SEARCH_CACHE_TTL = 180


def _cookiefile():
    return COOKIES_FILE if os.path.isfile(COOKIES_FILE) else None


def time_to_seconds(time):
    stringt = str(time)
    return sum(int(x) * 60 ** i for i, x in enumerate(reversed(stringt.split(":"))))


def _seconds_to_min(sec: int) -> str:
    if not sec:
        return "0:00"
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _format_views(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "Unknown Views"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B views"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M views"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K views"
    return f"{n} views"


def _base_opts():
    return {
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
        "cookiefile": _cookiefile(),
        "noplaylist": True,
    }


# ── Core: accurate YouTube search via yt-dlp (same engine as YouTube) ────────

def _ytdlp_search_sync(query: str, limit: int = 1) -> list:
    """
    Search YouTube using yt-dlp's native ytsearch — identical results to
    what YouTube itself returns, unlike youtubesearchpython / py_yt.
    """
    opts = {
        **_base_opts(),
        "extract_flat": True,
        "skip_download": True,
        "noplaylist": False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    entries = (info or {}).get("entries") or []
    results = []
    for entry in entries:
        if not entry or not entry.get("id"):
            continue
        vid_id = entry["id"]
        dur_sec = int(entry.get("duration") or 0)
        results.append({
            "id": vid_id,
            "title": entry.get("title") or "Unknown",
            "duration": _seconds_to_min(dur_sec),
            "duration_sec": dur_sec,
            "link": f"https://www.youtube.com/watch?v={vid_id}",
            "thumbnail": f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg",
            "channel": entry.get("uploader") or entry.get("channel") or "",
        })
    return results


async def _ytdlp_search(query: str, limit: int = 1) -> list:
    """Async wrapper for _ytdlp_search_sync with in-process caching."""
    cache_key = f"search:{limit}:{query}"
    cached = _SEARCH_CACHE.get(cache_key)
    if cached and _time.time() - cached[0] < _SEARCH_CACHE_TTL:
        return cached[1]
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _ytdlp_search_sync, query, limit)
    if results:
        _SEARCH_CACHE[cache_key] = (_time.time(), results)
    return results


def _ytdlp_video_info_sync(video_url: str) -> dict:
    """Full metadata extraction for a specific YouTube video URL."""
    opts = {**_base_opts(), "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
    return info or {}


async def _ytdlp_video_info(video_url: str) -> dict:
    cache_key = f"info:{video_url}"
    cached = _SEARCH_CACHE.get(cache_key)
    if cached and _time.time() - cached[0] < _SEARCH_CACHE_TTL:
        return cached[1]
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _ytdlp_video_info_sync, video_url)
    if info:
        _SEARCH_CACHE[cache_key] = (_time.time(), info)
    return info


# ── Download helpers ──────────────────────────────────────────────────────────

def _download_song_sync(video_id: str) -> str:
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")
    ydl_opts = {
        **_base_opts(),
        "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
        "outtmpl": outtmpl,
        "concurrent_fragment_downloads": 8,
        "socket_timeout": 10,
        "retries": 3,
        "fragment_retries": 3,
        "skip_unavailable_fragments": True,
        "prefer_free_formats": True,
        "buffersize": 1024 * 16,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
        filename = ydl.prepare_filename(info)
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        return filename
    return None


def _download_video_sync(video_id: str, file_path: str) -> bool:
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")
    ydl_opts = {
        **_base_opts(),
        "format": "bestvideo[height<=?720][ext=mp4]+bestaudio[ext=m4a]/best[height<=?720]",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "concurrent_fragment_downloads": 4,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    return os.path.exists(file_path) and os.path.getsize(file_path) > 0


def _find_cached(video_id: str) -> str:
    import glob
    for f in glob.glob(os.path.join(DOWNLOAD_DIR, f"{video_id}.*")):
        if os.path.getsize(f) > 0 and not f.endswith((".part", ".ytdl")):
            return f
    return None


async def download_song(link: str) -> str:
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
    if not video_id or len(video_id) < 3:
        return None
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    cached = _find_cached(video_id)
    if cached:
        return cached
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _download_song_sync, video_id)
    except Exception:
        return None


async def download_video(link: str) -> str:
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
    if not video_id or len(video_id) < 3:
        return None
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp4")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path
    loop = asyncio.get_event_loop()
    try:
        ok = await loop.run_in_executor(None, _download_video_sync, video_id, file_path)
        return file_path if ok else None
    except Exception:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return None


def _extract_related_sync(videoid: str):
    url = f"https://www.youtube.com/watch?v={videoid}&list=RD{videoid}"
    ydl_opts = {
        **_base_opts(),
        "extract_flat": True,
        "skip_download": True,
        "noplaylist": False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") or []
    results = []
    for entry in entries:
        if not entry:
            continue
        vid = entry.get("id")
        if not vid or vid == videoid:
            continue
        results.append({
            "id": vid,
            "title": entry.get("title") or "Unknown",
            "duration": entry.get("duration"),
        })
    return results


# ── YouTubeAPI class ──────────────────────────────────────────────────────────

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset: entity.offset + entity.length]
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = await _ytdlp_search(link, limit=1)
        if not results:
            raise ValueError(f"No results found for: {link}")
        r = results[0]
        return r["title"], r["duration"], r["duration_sec"], r["thumbnail"], r["id"]

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = await _ytdlp_search(link, limit=1)
        return results[0]["title"] if results else "Unknown"

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = await _ytdlp_search(link, limit=1)
        return results[0]["duration"] if results else "0:00"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = await _ytdlp_search(link, limit=1)
        return results[0]["thumbnail"] if results else None

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            downloaded_file = await download_video(link)
            if downloaded_file:
                return 1, downloaded_file
            return 0, "Video download failed"
        except Exception as e:
            return 0, f"Video download error: {e}"

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            plist = await Playlist.get(link)
        except Exception:
            return []
        videos = plist.get("videos") or []
        ids = []
        for data in videos[:limit]:
            if not data:
                continue
            vid = data.get("id")
            if not vid:
                continue
            ids.append(vid)
        return ids

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = await _ytdlp_search(link, limit=1)
        if not results:
            raise ValueError(f"No results found for: {link}")
        r = results[0]
        track_details = {
            "title": r["title"],
            "link": r["link"],
            "vidid": r["id"],
            "duration_min": r["duration"],
            "thumb": r["thumbnail"],
        }
        return track_details, r["id"]

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        ytdl_opts = {**_base_opts()}
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        with ydl:
            formats_available = []
            r = ydl.extract_info(link, download=False)
            for fmt in r["formats"]:
                try:
                    if "dash" not in str(fmt["format"]).lower():
                        formats_available.append({
                            "format": fmt["format"],
                            "filesize": fmt.get("filesize"),
                            "format_id": fmt["format_id"],
                            "ext": fmt["ext"],
                            "format_note": fmt["format_note"],
                            "yturl": link,
                        })
                except Exception:
                    continue
        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = await _ytdlp_search(link, limit=10)
        if not results or query_type >= len(results):
            raise ValueError("Not enough results")
        r = results[query_type]
        return r["title"], r["duration"], r["thumbnail"], r["id"]

    async def related(self, videoid: str):
        """Fetch related videos (YouTube Mix) for autoplay."""
        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(None, _extract_related_sync, videoid)
            random.shuffle(results)
            return results
        except Exception:
            return []

    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> str:
        if videoid:
            link = self.base + link
        try:
            if video:
                downloaded_file = await download_video(link)
            else:
                downloaded_file = await download_song(link)
            if downloaded_file:
                return downloaded_file, True
            return None, False
        except Exception:
            return None, False


YouTube = YouTubeAPI()
