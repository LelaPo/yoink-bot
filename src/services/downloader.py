import asyncio
import os
import time
from typing import Callable, Optional
import yt_dlp


def render_progress_bar(percent: float, length: int = 10) -> str:
    filled = int(length * (percent / 100))
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {percent:.1f}%"


class ThrottledProgressHook:
    def __init__(self, loop: asyncio.AbstractEventLoop, callback: Callable[[str], None]):
        self.loop = loop
        self.callback = callback
        self.last_update = 0.0

    def __call__(self, d: dict):
        if d.get("status") == "downloading":
            now = time.time()
            # обновляем UI не чаще чем раз в 1.8 секунды для соблюдения лимитов telegram
            if now - self.last_update < 1.8:
                return

            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = (downloaded / total) * 100
                mb_down = downloaded / (1024 * 1024)
                mb_total = total / (1024 * 1024)
                text = f"downloading {render_progress_bar(pct)} • {mb_down:.1f}/{mb_total:.1f} mb"
            else:
                mb_down = downloaded / (1024 * 1024)
                text = f"downloading • {mb_down:.1f} mb"

            self.last_update = now
            self.loop.call_soon_threadsafe(self.callback, text)


def download_media(
    url: str,
    mode: str,
    target_dir: str,
    loop: asyncio.AbstractEventLoop,
    progress_callback: Callable[[str], None],
) -> tuple[str, dict]:
    outtmpl = os.path.join(target_dir, "%(title).50s-%(id)s.%(ext)s")
    hook = ThrottledProgressHook(loop, progress_callback)

    ydl_opts: dict = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "progress_hooks": [hook],
    }

    if mode == "video":
        ydl_opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        ydl_opts["merge_output_format"] = "mp4"
    elif mode == "audio_mp3":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }
        ]
    elif mode == "audio_opus":
        # оригинальный лучший аудиопоток без пережимания
        ydl_opts["format"] = "bestaudio[ext=webm]/bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "opus",
            }
        ]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if "entries" in info:
            info = info["entries"][0]

    files = [
        os.path.join(target_dir, f)
        for f in os.listdir(target_dir)
        if not f.endswith(".part") and not f.endswith(".ytdl")
    ]
    if not files:
        raise RuntimeError("download produced no output file")

    files.sort(key=lambda p: os.path.getsize(p), reverse=True)
    return files[0], info