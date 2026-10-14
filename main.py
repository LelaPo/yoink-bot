import asyncio
import logging
import os
import re
import secrets
import shutil
import sys
import tempfile
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
import yt_dlp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    logging.error("yoink: BOT_TOKEN is required")
    sys.exit(1)

# parse comma-separated allowed user ids
ALLOWED_USER_IDS: set[int] = set()
_raw_allowed = os.getenv("ALLOWED_USER_IDS", "").strip()
if _raw_allowed:
    for item in _raw_allowed.split(","):
        cleaned = item.strip()
        if cleaned.isdigit():
            ALLOWED_USER_IDS.add(int(cleaned))

try:
    MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "50"))
except ValueError:
    MAX_FILE_MB = 50

DOWNLOAD_DIR = "/tmp/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# store pending urls by short token to stay within callback data limits
pending_urls: dict[str, str] = {}

YOUTUBE_PATTERN = re.compile(
    r"https?://(?:[a-zA-Z0-9_-]+\.)?(?:youtube\.com|youtu\.be)/\S+"
)

dp = Dispatcher()


def is_allowed(user_id: Optional[int]) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS


def extract_youtube_url(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = YOUTUBE_PATTERN.search(text)
    return match.group(0) if match else None


def run_download(url: str, mode: str, target_dir: str) -> str:
    # download media synchronously with yt-dlp
    outtmpl = os.path.join(target_dir, "%(title).50s-%(id)s.%(ext)s")
    ydl_opts: dict = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    if mode == "video":
        ydl_opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        ydl_opts["merge_output_format"] = "mp4"
    else:
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }
        ]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    files = [
        os.path.join(target_dir, f)
        for f in os.listdir(target_dir)
        if not f.endswith(".part") and not f.endswith(".ytdl")
    ]
    if not files:
        raise RuntimeError("no output file produced")

    files.sort(key=lambda p: os.path.getsize(p), reverse=True)
    return files[0]


@dp.message(CommandStart())
@dp.message(Command("help"))
async def handle_start_or_help(message: Message) -> None:
    if not is_allowed(message.from_user.id if message.from_user else None):
        await message.answer("yoink: access denied.")
        return
    await message.answer("yoink: send me a youtube link.")


@dp.message(F.text, ~F.text.startswith("/"))
async def handle_text(message: Message) -> None:
    if not is_allowed(message.from_user.id if message.from_user else None):
        await message.answer("yoink: access denied.")
        return

    url = extract_youtube_url(message.text)
    if not url:
        await message.answer("yoink: send a valid youtube link.")
        return

    token = secrets.token_hex(4)
    pending_urls[token] = url

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="video", callback_data=f"dl:video:{token}"),
                InlineKeyboardButton(text="audio", callback_data=f"dl:audio:{token}"),
            ]
        ]
    )
    await message.answer("yoink: pick a format.", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("dl:"))
async def handle_callback(callback: CallbackQuery) -> None:
    if not is_allowed(callback.from_user.id if callback.from_user else None):
        await callback.answer("yoink: access denied.")
        return

    parts = callback.data.split(":") if callback.data else []
    if len(parts) != 3:
        await callback.answer()
        return

    _, mode, token = parts
    url = pending_urls.pop(token, None)
    if not url:
        await callback.answer()
        if callback.message:
            await callback.message.answer("yoink: link expired.")
        return

    await callback.answer()
    if callback.message:
        await callback.message.answer("yoink: fetching, give it a moment.")

    # run blocking download in thread pool to avoid blocking the event loop
    loop = asyncio.get_running_loop()
    work_dir = tempfile.mkdtemp(dir=DOWNLOAD_DIR)
    try:
        file_path = await loop.run_in_executor(None, run_download, url, mode, work_dir)
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if size_mb > MAX_FILE_MB:
            if mode == "video" and callback.message:
                await callback.message.answer(
                    "yoink: that file is over the size limit, try audio."
                )
            elif callback.message:
                await callback.message.answer("yoink: that file is over the size limit.")
            return

        payload = FSInputFile(file_path)
        if callback.message:
            if mode == "video":
                await callback.message.answer_video(payload)
            else:
                await callback.message.answer_audio(payload)
    except Exception as exc:
        logging.warning("yoink: download error: %s", exc)
        if callback.message:
            await callback.message.answer("yoink: download failed.")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    logging.info("yoink: starting bot")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())