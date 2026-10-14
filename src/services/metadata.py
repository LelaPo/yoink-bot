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


def format_count(count: Optional[int]) -> str:
    if not count:
        return ""
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}b"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}m"
    if count >= 1_000:
        return f"{count / 1_000:.1f}k"
    return str(count)


def humanize_vcodec(vcodec: Optional[str]) -> str:
    if not vcodec:
        return "h.264"
    c = vcodec.lower()
    if c.startswith("av01"):
        parts = c.split(".")
        bitdepth = f" ({parts[3]}-bit)" if len(parts) > 3 and parts[3].isdigit() else ""
        return f"av1{bitdepth}"
    if c.startswith("avc1") or "h264" in c:
        return "h.264"
    if c.startswith("vp09") or "vp9" in c:
        return "vp9"
    if c.startswith("vp08") or "vp8" in c:
        return "vp8"
    if "hevc" in c or c.startswith("hvc1") or "h265" in c:
        return "h.265"
    return c.split(".")[0]


def humanize_acodec(acodec: Optional[str]) -> str:
    if not acodec:
        return "aac"
    c = acodec.lower()
    if "mp4a.40.2" in c or "aac" in c:
        return "aac lc"
    if "opus" in c:
        return "opus"
    if "mp3" in c:
        return "mp3"
    return c.split(".")[0]


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
    uploader = str(info.get("uploader") or info.get("channel") or "").strip().lower()
    duration = format_duration(info.get("duration"))
    views = format_count(info.get("view_count"))

    width = info.get("width")
    height = info.get("height")
    res = f"{width}x{height}" if width and height else "720p"
    fps = info.get("fps")
    fps_str = f" @ {int(fps)}fps" if fps else ""

    vcodec = humanize_vcodec(info.get("vcodec"))
    acodec = humanize_acodec(info.get("acodec"))

    tbr = info.get("tbr")
    bitrate_str = f", ~{int(tbr)} kbps" if tbr else ""

    lines = [f"title: {title[:70]}"]
    if uploader:
        lines.append(f"channel: {uploader[:40]}")

    meta = [f"duration: {duration}", f"size: {size_mb:.1f} mb"]
    if views:
        meta.append(f"views: {views}")
    lines.append(" • ".join(meta))

    lines.append(f"video: {vcodec} ({res}{fps_str}{bitrate_str})")
    lines.append(f"audio: {acodec}")
    lines.append("container: mp4")

    return "\n".join(lines)


def build_audio_caption(
    artist: str,
    title: str,
    duration_sec: int,
    size_mb: float,
    fmt: str,
    views_count: Optional[int] = None,
) -> str:
    lines = [
        f"track: {title.lower()[:60]}",
        f"artist: {artist.lower()[:60]}",
        f"duration: {format_duration(duration_sec)} • size: {size_mb:.1f} mb",
        f"format: {fmt}",
    ]
    views = format_count(views_count)
    if views:
        lines.append(f"views: {views}")
    return "\n".join(lines)