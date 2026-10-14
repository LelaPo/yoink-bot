import os
import urllib.request
from typing import Optional
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC
from mutagen.mp4 import MP4, MP4Cover


def format_duration(seconds: Optional[int | float]) -> str:
    if not seconds:
        return "00:00"
    secs = int(seconds)
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def parse_track_info(raw_title: str, uploader: str) -> tuple[str, str]:
    cleaned = raw_title.strip()
    if " - " in cleaned:
        artist, title = cleaned.split(" - ", 1)
        return artist.strip(), title.strip()
    return uploader.strip(), cleaned


def download_cover(url: Optional[str], target_path: str) -> Optional[str]:
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp, open(target_path, "wb") as f:
            f.write(resp.read())
        return target_path
    except Exception:
        return None


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

    elif ext == ".m4a":
        try:
            tags = MP4(file_path)
            tags["\xa9ART"] = artist
            tags["\xa9nam"] = title
            if cover_path and os.path.exists(cover_path):
                with open(cover_path, "rb") as img:
                    tags["covr"] = [MP4Cover(img.read(), imageformat=MP4Cover.FORMAT_JPEG)]
            tags.save()
        except Exception:
            pass


def build_video_caption(info: dict, size_mb: float) -> str:
    title = str(info.get("title") or "video").strip().lower()
    duration = format_duration(info.get("duration"))
    width = info.get("width")
    height = info.get("height")
    res = f"{width}x{height}" if width and height else "720p"
    fps = info.get("fps")
    fps_str = f" @ {int(fps)}fps" if fps else ""
    vcodec = str(info.get("vcodec") or "h264").lower()
    acodec = str(info.get("acodec") or "aac").lower()

    if "avc" in vcodec:
        vcodec = "h264"
    elif "vp09" in vcodec:
        vcodec = "vp9"
    if "mp4a" in acodec:
        acodec = "aac"

    return "\n".join([
        f"title: {title[:70]}",
        f"duration: {duration}",
        f"size: {size_mb:.1f} mb",
        "container: mp4",
        f"video: {vcodec} {res}{fps_str}",
        f"audio: {acodec}",
    ])


def build_audio_caption(artist: str, title: str, duration_sec: int, size_mb: float, fmt: str) -> str:
    return "\n".join([
        f"track: {title.lower()[:60]}",
        f"artist: {artist.lower()[:60]}",
        f"duration: {format_duration(duration_sec)}",
        f"size: {size_mb:.1f} mb",
        f"format: {fmt}",
    ])