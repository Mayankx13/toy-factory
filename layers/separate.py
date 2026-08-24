"""Split a track into stems (drums / bass / vocals / other) with Demucs.

Runs demucs as a subprocess so its model download + progress bars stream
cleanly, and so a crash can't take the whole pipeline down. Tries Apple's MPS
GPU first and falls back to CPU — some FFT ops historically lacked MPS kernels.
"""

import shutil
import subprocess
import sys
from pathlib import Path

STEMS = ["drums", "bass", "vocals", "other"]
MODEL = "htdemucs"


def _run(wav_path: Path, tmp: Path, device: str) -> None:
    cmd = [
        sys.executable, "-m", "demucs.separate",
        "-n", MODEL,
        "-d", device,
        "--mp3", "--mp3-bitrate", "192",
        "--filename", "{stem}.{ext}",
        "-o", str(tmp),
        str(wav_path),
    ]
    subprocess.run(cmd, check=True)


def separate(wav_path: Path, out_dir: Path) -> dict:
    """Return {stem_name: mp3_path} under out_dir/stems/."""
    import torch

    tmp = out_dir / "_demucs"
    if tmp.exists():
        shutil.rmtree(tmp)

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    try:
        _run(wav_path, tmp, device)
    except subprocess.CalledProcessError:
        if device == "cpu":
            raise
        print("[separate] MPS failed, retrying on CPU…", flush=True)
        _run(wav_path, tmp, "cpu")

    stems_dir = out_dir / "stems"
    stems_dir.mkdir(exist_ok=True)
    result = {}
    for stem in STEMS:
        src = tmp / MODEL / f"{stem}.mp3"
        dest = stems_dir / f"{stem}.mp3"
        shutil.move(str(src), dest)
        result[stem] = dest
    shutil.rmtree(tmp)
    return result
