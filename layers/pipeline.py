"""The four stages in order, driven by either the CLI or the local server.

Both front-ends call run() so there is exactly one description of what
"deconstruct a track" means. Progress arrives through an on_event callback
rather than prints, because the server needs to forward it to a browser.
"""

import json
import shutil
from pathlib import Path

from . import analyze as analyze_mod
from . import download, report, separate

STAGES = ["download", "prepare", "separate", "analyze", "report"]


def _noop(stage, detail="", pct=None):
    pass


def run(target=None, file=None, out_root="output", start=None, duration=None, on_event=_noop):
    """Fetch, split, measure and render one track. Returns (data, run_dir, html)."""
    out_root = Path(out_root)
    staging = out_root / "_incoming"
    if staging.exists():
        shutil.rmtree(staging)

    if file:
        src = Path(file).expanduser()
        if not src.exists():
            raise FileNotFoundError(f"no such file: {src}")
        on_event("download", f"importing {src.name}")
        mp3, meta = download.import_local(src, staging)
    else:
        on_event("download", "asking YouTube for the audio", 0)

        def hook(d):
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                if total:
                    on_event("download", "downloading audio", d.get("downloaded_bytes", 0) / total * 100)
            elif d.get("status") == "finished":
                on_event("download", "converting to mp3", 100)

        mp3, meta = download.fetch_youtube(target, staging, progress_hook=hook)

    run_dir = out_root / download.slugify(meta["title"])
    run_dir.mkdir(parents=True, exist_ok=True)
    source = run_dir / "source.mp3"
    shutil.move(str(mp3), source)
    shutil.rmtree(staging, ignore_errors=True)

    on_event("prepare", "rendering the analysis wav")
    wav = download.to_wav(source, run_dir / "analysis.wav", start, duration)
    if start or duration:
        download.to_mp3(wav, source)

    on_event("separate", "loading the Demucs model", 0)
    stems = separate.separate(
        wav, run_dir,
        on_progress=lambda p: on_event("separate", "splitting into four stems", p),
    )

    on_event("analyze", "measuring what each layer does")
    data = analyze_mod.analyze(wav, stems, meta)
    (run_dir / "analysis.json").write_text(json.dumps(data, indent=1))

    on_event("report", "building the page")
    html = report.render(data, run_dir)
    wav.unlink(missing_ok=True)

    on_event("done", data["meta"]["title"], 100)
    return data, run_dir, html
