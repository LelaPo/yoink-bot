import asyncio
import os
import re
import secrets
import shutil
import tempfile
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto, Message

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
from services.recognition import recognize_track

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


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.delete()


@router.message(AudioEditState.waiting_title)
async def process_new_title(message: Message, state: FSMContext):
    data = await state.get_data()
    token = data.get("token")
    task = pending_tasks.get(token) if token else None
    if not task:
        await state.clear()
        return

    task["title"] = message.text.strip()
    task["source"] = "manual"
    await message.delete()
    await state.clear()

    caption = build_audio_caption(
        task["artist"],
        task["title"],
        task["duration"],
        task["size_mb"],
        task["fmt_name"],
        task.get("views"),
        task["source"],
    )

    try:
        if task.get("has_cover"):
            await message.bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=task["preview_msg_id"],
                caption=caption,
                reply_markup=tag_editor_kb(token),
            )
        else:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=task["preview_msg_id"],
                text=caption,
                reply_markup=tag_editor_kb(token),
            )
    except Exception:
        pass


@router.message(AudioEditState.waiting_artist)
async def process_new_artist(message: Message, state: FSMContext):
    data = await state.get_data()
    token = data.get("token")
    task = pending_tasks.get(token) if token else None
    if not task:
        await state.clear()
        return

    task["artist"] = message.text.strip()
    task["source"] = "manual"
    await message.delete()
    await state.clear()

    caption = build_audio_caption(
        task["artist"],
        task["title"],
        task["duration"],
        task["size_mb"],
        task["fmt_name"],
        task.get("views"),
        task["source"],
    )

    try:
        if task.get("has_cover"):
            await message.bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=task["preview_msg_id"],
                caption=caption,
                reply_markup=tag_editor_kb(token),
            )
        else:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=task["preview_msg_id"],
                text=caption,
                reply_markup=tag_editor_kb(token),
            )
    except Exception:
        pass


@router.message(AudioEditState.waiting_cover, F.photo)
async def process_new_cover_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    token = data.get("token")
    task = pending_tasks.get(token) if token else None
    if not task:
        await state.clear()
        return

    photo = message.photo[-1]
    custom_cover = os.path.join(task["work_dir"], "custom_cover.jpg")
    await message.bot.download(photo, destination=custom_cover)

    task["cover_path"] = custom_cover
    task["has_cover"] = True
    task["source"] = "custom"
    await message.delete()
    await state.clear()

    caption = build_audio_caption(
        task["artist"],
        task["title"],
        task["duration"],
        task["size_mb"],
        task["fmt_name"],
        task.get("views"),
        task["source"],
    )

    try:
        await message.bot.edit_message_media(
            chat_id=message.chat.id,
            message_id=task["preview_msg_id"],
            media=InputMediaPhoto(
                media=FSInputFile(custom_cover),
                caption=caption,
            ),
            reply_markup=tag_editor_kb(token),
        )
    except Exception:
        pass


@router.message(AudioEditState.waiting_cover, F.document)
async def process_new_cover_doc(message: Message, state: FSMContext):
    data = await state.get_data()
    token = data.get("token")
    task = pending_tasks.get(token) if token else None
    if not task:
        await state.clear()
        return

    doc = message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await message.delete()
        return

    ext = ".png" if "png" in doc.mime_type else ".jpg"
    custom_cover = os.path.join(task["work_dir"], f"custom_cover{ext}")
    await message.bot.download(doc, destination=custom_cover)

    task["cover_path"] = custom_cover
    task["has_cover"] = True
    task["source"] = "custom"
    await message.delete()
    await state.clear()

    caption = build_audio_caption(
        task["artist"],
        task["title"],
        task["duration"],
        task["size_mb"],
        task["fmt_name"],
        task.get("views"),
        task["source"],
    )

    try:
        await message.bot.edit_message_media(
            chat_id=message.chat.id,
            message_id=task["preview_msg_id"],
            media=InputMediaPhoto(
                media=FSInputFile(custom_cover),
                caption=caption,
            ),
            reply_markup=tag_editor_kb(token),
        )
    except Exception:
        pass


@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
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

        if mode == "video":
            caption = build_video_caption(info, size_mb)
            payload = FSInputFile(file_path)
            await callback.message.answer_video(payload, caption=caption)
            await status_msg.delete()
            shutil.rmtree(work_dir, ignore_errors=True)
            pending_tasks.pop(token, None)
            return

        # для аудио по умолчанию берем метаданные youtube
        raw_title = info.get("title") or "track"
        uploader = info.get("uploader") or info.get("channel") or "artist"
        artist, title = parse_track_info(raw_title, uploader)
        duration = int(info.get("duration") or 0)
        views = info.get("view_count")

        cover_path = os.path.join(work_dir, "orig_cover.jpg")
        has_cover = download_cover(info.get("thumbnail"), cover_path) is not None

        fmt_name = "mp3 (320 kbps)" if mode == "audio_mp3" else "m4a (source aac)"
        caption = build_audio_caption(artist, title, duration, size_mb, fmt_name, views, "youtube")

        task.update({
            "file_path": file_path,
            "work_dir": work_dir,
            "cover_path": cover_path if has_cover else None,
            "orig_cover_path": cover_path if has_cover else None,
            "has_cover": has_cover,
            "artist": artist,
            "orig_artist": artist,
            "title": title,
            "orig_title": title,
            "duration": duration,
            "size_mb": size_mb,
            "fmt_name": fmt_name,
            "views": views,
            "source": "youtube",
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

    elif action == "cover":
        await state.set_state(AudioEditState.waiting_cover)
        await state.update_data(token=token)
        await callback.answer("send new cover image in chat.")

    elif action == "shazam":
        await callback.answer("scanning fingerprint...")
        recognized = await recognize_track(task["file_path"])
        if not recognized:
            await callback.answer("no match found in shazam.", show_alert=True)
            return

        task["title"] = recognized["title"]
        task["artist"] = recognized["artist"]
        task["source"] = "shazam"

        if recognized.get("cover_url"):
            shazam_cover = os.path.join(task["work_dir"], "shazam_cover.jpg")
            if download_cover(recognized["cover_url"], shazam_cover):
                task["cover_path"] = shazam_cover
                task["has_cover"] = True

        caption = build_audio_caption(
            task["artist"],
            task["title"],
            task["duration"],
            task["size_mb"],
            task["fmt_name"],
            task.get("views"),
            task["source"],
        )

        try:
            if task.get("cover_path"):
                await callback.message.edit_media(
                    media=InputMediaPhoto(
                        media=FSInputFile(task["cover_path"]),
                        caption=caption,
                    ),
                    reply_markup=tag_editor_kb(token),
                )
            else:
                await callback.message.edit_caption(
                    caption=caption,
                    reply_markup=tag_editor_kb(token),
                )
        except Exception:
            pass
        await callback.answer("matched with shazam.")

    elif action == "reset":
        # полный возврат к исходным метаданным youtube
        task["artist"] = task["orig_artist"]
        task["title"] = task["orig_title"]
        task["cover_path"] = task["orig_cover_path"]
        task["has_cover"] = task["orig_cover_path"] is not None
        task["source"] = "youtube"

        caption = build_audio_caption(
            task["artist"],
            task["t