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
from services.metadata import apply_audio_tags, parse_track_info

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
async def handle_link(message: Message, state: FSMContext):
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
async def handle_download_choice(callback: CallbackQuery, state: FSMContext):
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
    loop = asyncio.get_running_loop()

    # колбэк троттлированного прогресса
    async def update_progress(text: str):
        try:
            await status_msg.edit_text(text)
        except Exception:
            pass

    def on_progress(text: str):
        asyncio.run_coroutine_threadsafe(update_progress(text), loop)

    await status_msg.edit_text("downloading [░░░░░░░░░░] 0%")

    work_dir = tempfile.mkdtemp(dir=config.download_dir)
    try:
        file_path, info = await loop.run_in_executor(
            None, download_media, task["url"], mode, work_dir, loop, on_progress
        )

        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if size_mb > config.max_file_mb:
            await status_msg.edit_text(f"file is over {config.max_file_mb} mb limit.")
            shutil.rmtree(work_dir, ignore_errors=True)
            return

        # если аудио — даем возможность быстро подправить теги или отправить
        if mode.startswith("audio_"):
            raw_title = info.get("title") or "track"
            uploader = info.get("uploader") or "artist"
            artist, title = parse_track_info(raw_title, uploader)

            task.update({
                "file_path": file_path,
                "work_dir": work_dir,
                "artist": artist,
                "title": title,
                "duration": int(info.get("duration") or 0),
            })

            text = f"audio ready:\nartist: {artist}\ntitle: {title}"
            await status_msg.edit_text(text, reply_markup=tag_editor_kb(token))
            return

        # для видео — сразу показываем yoinked! и выдаем файл
        await status_msg.edit_text("yoinked!")
        await asyncio.sleep(0.8)

        payload = FSInputFile(file_path)
        caption = f"{info.get('title', 'video')}\n{size_mb:.1f} mb"
        await callback.message.answer_video(payload, caption=caption)
        await status_msg.delete()  # удаляем служебное сообщение

    except Exception:
        await status_msg.edit_text("download failed.")
    finally:
        if not mode.startswith("audio_"):
            shutil.rmtree(work_dir, ignore_errors=True)


# fsm редактор метатегов
@router.callback_query(F.data.startswith("tag:"))
async def handle_tag_actions(callback: CallbackQuery, state: FSMContext):
    _, action, token = callback.data.split(":")
    task = pending_tasks.get(token)
    if not task:
        await callback.answer("task expired.")
        return

    if action == "title":
        await state.set_state(AudioEditState.waiting_title)
        await state.update_data(token=token, msg_id=callback.message.message_id)
        await callback.message.edit_text(f"send new title for '{task['title']}':")

    elif action == "artist":
        await state.set_state(AudioEditState.waiting_artist)
        await state.update_data(token=token, msg_id=callback.message.message_id)
        await callback.message.edit_text(f"send new artist for '{task['artist']}':")

    elif action == "send":
        await callback.answer()
        await callback.message.edit_text("yoinked!")
        await asyncio.sleep(0.8)

        # применяем теги в файл
        apply_audio_tags(task["file_path"], task["artist"], task["title"])

        payload = FSInputFile(task["file_path"])
        await callback.message.answer_audio(
            payload,
            title=task["title"],
            performer=task["artist"],
            duration=task["duration"],
        )
        await callback.message.delete()
        shutil.rmtree(task["work_dir"], ignore_errors=True)
        pending_tasks.pop(token, None)


@router.message(AudioEditState.waiting_title)
async def process_new_title(message: Message, state: FSMContext):
    data = await state.get_data()
    token = data["token"]
    task = pending_tasks[token]
    task["title"] = message.text.strip()
    await message.delete()  # удаляем сообщение пользователя, чтобы чат не засорялся

    await state.clear()
    text = f"audio ready:\nartist: {task['artist']}\ntitle: {task['title']}"
    await message.bot.edit_message_text(
        text=text,
        chat_id=message.chat.id,
        message_id=data["msg_id"],
        reply_markup=tag_editor_kb(token),
    )


@router.message(AudioEditState.waiting_artist)
async def process_new_artist(message: Message, state: FSMContext):
    data = await state.get_data()
    token = data["token"]
    task = pending_tasks[token]
    task["artist"] = message.text.strip()
    await message.delete()

    await state.clear()
    text = f"audio ready:\nartist: {task['artist']}\ntitle: {task['title']}"
    await message.bot.edit_message_text(
        text=text,
        chat_id=message.chat.id,
        message_id=data["msg_id"],
        reply_markup=tag_editor_kb(token),
    )