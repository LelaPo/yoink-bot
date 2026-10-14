import os
import yt_dlp


def download_media(url: str, mode: str, target_dir: str) -> tuple[str, dict]:
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
    elif mode == "audio_mp3":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }
        ]
    elif mode == "audio_m4a":
        # оригинальный aac аудиопоток с youtube без перекодирования
        ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
            }
        ]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if "entries" in info:
            info = info["entries"][0]

    files = [
        os.path.join(target_dir, f)
        for f in os.listdir(target_dir)
        if not f.endswith((".part", ".ytdl", ".jpg", ".png", ".webp"))
    ]
    if not files:
        raise RuntimeError("download produced no media file")

    files.sort(key=lambda p: os.path.getsize(p), reverse=True)
    return files[0], info