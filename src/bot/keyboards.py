from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def format_picker_kb(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="mp4 (720p)", callback_data=f"dl:video:{token}"),
            ],
            [
                InlineKeyboardButton(text="mp3 (320k)", callback_data=f"dl:audio_mp3:{token}"),
                InlineKeyboardButton(text="m4a (source)", callback_data=f"dl:audio_m4a:{token}"),
            ],
        ]
    )


def tag_editor_kb(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="edit title", callback_data=f"tag:title:{token}"),
                InlineKeyboardButton(text="edit artist", callback_data=f"tag:artist:{token}"),
            ],
            [
                InlineKeyboardButton(text="edit cover", callback_data=f"tag:cover:{token}"),
                InlineKeyboardButton(text="shazam again", callback_data=f"tag:shazam:{token}"),
            ],
            [
                InlineKeyboardButton(text="send audio", callback_data=f"tag:send:{token}"),
            ],
        ]
    )