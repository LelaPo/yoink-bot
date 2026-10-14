import os
from typing import Optional
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC
from mutagen.oggopus import OggOpus


def parse_track_info(raw_title: str, uploader: str) -> tuple[str, str]:
    if " - " in raw_title:
        parts = raw_title.split(" - ", 1)
        return parts[0].strip(), parts[1].strip()
    return uploader.strip(), raw_title.strip()


def apply_audio_tags(
    file_path: str,
    artist: str,
    title: str,
    cover_path: Optional[str] = None,
) -> None:
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".mp3":
        try:
            tags = EasyID3(file_path)
        except Exception:
            tags = EasyID3()
        tags["artist"] = artist
        tags["title"] = title
        tags.save(file_path)

        if cover_path and os.path.exists(cover_path):
            audio = ID3(file_path)
            with open(cover_path, "rb") as img:
                audio["APIC"] = APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,
                    desc="Cover",
                    data=img.read(),
                )
            audio.save(file_path)

    elif ext == ".opus":
        try:
            audio = OggOpus(file_path)
            audio["artist"] = artist
            audio["title"] = title
            audio.save()
        except Exception:
            pass