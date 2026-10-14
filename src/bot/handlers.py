import asyncio
import os
import re
import secrets
import shutil
import tempfile
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from config import config
from bot.keyboards import format_picker_kb, tag_editor_kb
from bot.states import AudioEditState
from services.downloader import download_media
from services.metadata import (
    apply_audio_tags,
    build_audio_caption,
    build_video_caption,
    download_cover,
    parse_track_info,
)

router = Router()

pending_tasks: dict[str, dict] = {}
YOUTUBE_RE = re.compile(r"https?://(?:[a-zA-Z0-9_-]+\.)?(?:youtube\.com|youtu\.be)/\S+")


def is_allowed(user_id: Optional[int]) -> bool:
    if not config.allowed_user_ids:
        return True
    return user_id in config.allowed_user_ids


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_start(message: Message):
    if not is_allowed(message.from_user.id if message.from_user else None):
        await message.answer("access denied.")
        return
    await message.answer("send me a youtube link.")


@router.message(F.text, ~F.text.startswith("/"))
async def handle_link(message: Message):
    if not is_allowed(message.from_user.id if message.from_user else None):
        await message.answer("access denied.")
        return

    match = YOUTUBE_RE.search(message.text)
    if not match:
        await message.answer("send a valid youtube link.")
        return

    token = secrets.token_hex(4)
    pending_tasks[token] = {
        "url": match.group(0),
        "user_id": message.from_user.id,
    }

    await message.answer("pick format:", reply_markup=format_picker_kb(token))


@router.callback_query(F.data.startswith("dl:"))
async def handle_download_choice(callback: CallbackQuery):
    if not is_allowed(callback.from_user.id if callback.from_user else None):
        await callback.answer("access denied.")
        return

    _, mode, token = callback.data.split(":")
    task = pending_tasks.get(token)
    if not task:
        await callback.answer("link expired.")
        if callback.message:
            await callback.message.delete()
        return

    await callback.answer()
    status_msg = callback.message
    await status_msg.edit_text("fetching media...")

    loop = asyncio.get_running_loop()
    work_dir = tempfile.mkdtemp(dir=config.download_dir)

    try:
        file_path, info = await loop.run_in_executor(
            None, download_media, task["url"], mode, work_dir
        )

        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if size_mb > config.max_file_mb:
            await status_msg.edit_text(f"file exceeds {config.max_file_mb} mb limit.")
            shutil.rmtree(work_dir, ignore_errors=True)
            return

        # видео: отдаем сразу с полной карточкой характеристик
        if mode == "video":
            caption = build_video_caption(info, size_mb)
            payload = FSInputFile(file_path)
            await callback.message.answer_video(payload, caption=caption)
            await status_msg.delete()
            shutil.rmtree(work_dir, ignore_errors=True)
            pending_tasks.pop(token, None)
            return

        # аудио: скачиваем обложку и открываем интерактивную карточку
        raw_title = info.get("title") or "track"
        uploader = info.get("uploader") or "artist"
        artist, title = parse_track_info(raw_title, uploader)
        duration = int(info.get("duration") or 0)

        cover_path = os.path.join(work_dir, "cover.jpg")
        has_cover = download_cover(info.get("thumbnail"), cover_path) is not None

        fmt_name = "mp3 (320 kbps)" if mode == "audio_mp3" else "m4a (source aac)"
        caption = build_audio_caption(artist, title, duration, size_mb, fmt_name)

        task.update({
            "file_path": file_path,
            "work_dir": work_dir,
            "cover_path": cover_path if has_cover else None,
            "artist": artist,
            "title": title,
            "duration": duration,
            "size_mb": size_mb,
            "fmt_name": fmt_name,
        })

        await status_msg.delete()
        if has_cover:
            preview = await callback.message.answer_photo(
                FSInputFile(cover_path),
                caption=caption,
                reply_markup=tag_editor_kb(token),
            )
        else:
            preview = await callback.message.answer(
                caption,
                reply_markup=tag_editor_kb(token),
            )
        task["preview_msg_id"] = preview.message_id

    except Exception:
        await status_msg.edit_text("download failed.")
        shutil.rmtree(work_dir, ignore_errors=True)


@router.callback_query(F.data.startswith("tag:"))
async def handle_tag_actions(callback: CallbackQuery, state: FSMContext):
    _, action, token = callback.data.split(":")
    task = pending_tasks.get(token)
    if not task:
        await callback.answer("task expired.")
        return

    if action == "title":
        await state.set_state(AudioEditState.waiting_title)
        await state.update_data(token=token)
        await callback.answer("send new title in chat.")

    elif action == "artist":
        await state.set_state(AudioEditState.waiting_artist)
        await state.update_data(token=token)
        await callback.answer("send new artist in chat.")

    elif action == "send":
        await callback.answer()
        # удаляем карточку редактирования
        if callback.message:
            await callback.message.delete()

        # вшиваем теги и обложку в файл
        apply_audio_tags(
            task["file_path"],
            task["artist"],
            task["title"],
            task.get("cover_path"),
        )

        payload = FSInputFile(task["file_path"])
        thumb = FSInputFile(task["cover_path"]) if task.get("cover_path") else None

        await callback.message.answer_audio(
            payload,
            title=task["title"],
            performer=task["artist"],
            duration=task["duration"],
            thumbnail=thumb,
        )

        shutil.rmtree(task["work_dir"], ignore_errors=True)
        pending_tasks.pop(token, None)


@router.message(AudioEditState.waiting_title)
async def process_new_title(message: Message, state: FSMContext):
    data = await state.get_data()
    token = data["token"]
    task = pending_tasks.get(token)
    if not task:
        await state.clear()
        return

    task["title"] = message.text.strip()
    await message.delete()  # удаляем ввод пользователя
    await state.clear()

    caption = build_audio_caption(
        task["artist"], task["title"], task["duration"], task["size_mb"], task["fmt_name"]
    )
    await message.bot.edit_message_caption(
        chat_id=message.chat.id,
        message_id=task["preview_msg_id"],
        caption=caption,
        reply_markup=tag_editor_kb(token),
    )


@router.message(AudioEditState.waiting_artist)
async def process_new_artist(message: Message, state: FSMContext):
    data = await state.get_data()
    token = data["token"]
    task = pending_tasks.get(token)
    if not task:
        await state.clear()
        return

    task["artist"] = message.text.strip()
    await message.delete()
    await state.clear()

    caption = build_audio_caption(
        task["artist"], task["title"], task["duration"], task["size_mb"], task["fmt_name"]
    )
    await message.bot.edit_message_caption(
        chat_id=message.chat.id,
        message_id=task["preview_msg_id"],
        caption=caption,
        reply_markup=tag_editor_kb(token),
    )