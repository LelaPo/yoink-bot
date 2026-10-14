import logging
from typing import Optional
from shazamio import Shazam

shazam = Shazam()


async def recognize_track(file_path: str) -> Optional[dict]:
    try:
        out = await shazam.recognize(file_path)
        track = out.get("track")
        if not track:
            return None

        title = track.get("title")
        artist = track.get("subtitle")
        images = track.get("images") or {}
        # берем hq обложку альбома, если доступна
        cover_url = images.get("coverarthq") or images.get("coverart")

        return {
            "title": title,
            "artist": artist,
            "cover_url": cover_url,
        }
    except Exception as exc:
        logging.warning("shazam recognition error: %s", exc)
        return None