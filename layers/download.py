"""Fetch audio from YouTube (or use a local file) and render mp3 + analysis wav.

ffmpeg comes from the `static-ffmpeg` package, which downloads a self-contained
binary on first use — no Homebrew required on this machine.
"""

import re
import shutil
import subprocess
from pathlib import Path

_FFMPEG = None


def ffmpeg_path() -> str:
    global _FFMPEG
    if _FFMPEG is None:
        from static_ffmpeg import run

        ffmpeg, _ffprobe = run.get_or_fetch_platform_executables_else_raise()
        _FFMPEG = ffmpeg
    return _FFMPEG


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60] or "track"


def fetch_youtube(target: str, workdir: Path, progress_hook=None) -> tuple[Path, dict]:
    """Download best audio for a URL or search phrase; return (mp3_path, meta)."""
    import yt_dlp

    workdir.mkdir(parents=True, exist_ok=True)
    opts = {
        "quiet": progress_hook is not None,
        "progress_hooks": [progress_hook] if progress_hook else [],
        "format": "bestaudio/best",
        "outtmpl": str(workdir / "source.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ],
        "ffmpeg_location": str(Path(ffmpeg_path()).parent),
        "noplaylist": True,
        "default_search": "ytsearch1",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(target, download=True)
    if info.get("entries"):
        info = info["entries"][0]
    meta = {
        "title": info.get("title") or "Unknown title",
        "artist": info.get("artist") or info.get("uploader") or info.get("channel") or "",
        "url": info.get("webpage_url") or target,
        "duration": info.get("duration") or 0,
    }
    return workdir / "source.mp3", meta


def import_local(path: Path, workdir: Path) -> tuple[Path, dict]:
    """Bring a local audio file into the working directory as source.mp3."""
    workdir.mkdir(parents=True, exist_ok=True)
    dest = workdir / "source.mp3"
    if path.suffix.lower() == ".mp3":
        shutil.copy(path, dest)
    else:
        subprocess.run(
            [ffmpeg_path(), "-y", "-i", str(path), "-codec:a", "libmp3lame", "-b:a", "192k", str(dest)],
            check=True,
            capture_output=True,
        )
    meta = {"title": path.stem, "artist": "", "url": str(path), "duration": 0}
    return dest, meta


def to_wav(src: Path, dest: Path, start: float | None = None, duration: float | None = None) -> Path:
    """Render a 44.1 kHz stereo wav — the format Demucs and librosa both read natively."""
    cmd = [ffmpeg_path(), "-y", "-i", str(src)]
    if start:
        cmd += ["-ss", str(start)]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-ac", "2", "-ar", "44100", str(dest)]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest


def to_mp3(src: Path, dest: Path) -> Path:
    subprocess.run(
        [ffmpeg_path(), "-y", "-i", str(src), "-codec:a", "libmp3lame", "-b:a", "192k", str(dest)],
        check=True,
        capture_output=True,
    )
    return dest
