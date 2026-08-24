"""Split a track into stems (drums / bass / vocals / other) with Demucs.

Runs demucs as a subprocess so its model download + progress bars stream
cleanly, and so a crash can't take the whole pipeline down. Tries Apple's MPS
GPU first and falls back to CPU — some FFT ops historically lacked MPS kernels.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

STEMS = ["drums", "bass", "vocals", "other"]
MODEL = "htdemucs"


def _run(wav_path: Path, tmp: Path, device: str, on_progress=None) -> None:
    cmd = [
        sys.executable, "-m", "demucs.separate",
        "-n", MODEL,
        "-d", device,
        "--mp3", "--mp3-bitrate", "192",
        "--filename", "{stem}.{ext}",
        "-o", str(tmp),
        str(wav_path),
    ]
    if on_progress is None:
        subprocess.run(cmd, check=True)
        return

    # demucs draws a tqdm bar on stderr with carriage returns and no newlines,
    # so read characters rather than lines and pick the last percentage seen.
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            text=True, errors="replace")
    buf, last = "", -1
    while True:
        ch = proc.stderr.read(1)
        if not ch:
            break
        buf += ch
        if ch == "%":
            m = re.search(r"(\d{1,3})%$", buf)
            if m and int(m.group(1)) != last:
                last = int(m.group(1))
                on_progress(float(last))
            buf = buf[-16:]
        elif len(buf) > 4096:
            buf = buf[-16:]
    if proc.wait() != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


def separate(wav_path: Path, out_dir: Path, on_progress=None) -> dict:
    """Return {stem_name: mp3_path} under out_dir/stems/."""
    import torch

    tmp = out_dir / "_demucs"
    if tmp.exists():
        shutil.rmtree(tmp)

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    try:
        _run(wav_path, tmp, device, on_progress)
    except subprocess.CalledProcessError:
        if device == "cpu":
            raise
        print("[separate] MPS failed, retrying on CPU…", flush=True)
        _run(wav_path, tmp, "cpu", on_progress)

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
