"""Command line entry point: a URL or a file in, a playable report out.

    python -m layers "aphex twin xtal"
    python -m layers https://youtu.be/... --start 30 --duration 60
    python -m layers --file ~/Music/demo.wav
    python -m layers --report-only output/xtal      # re-render, skip the slow parts
"""

import argparse
import json
import shutil
import sys
import webbrowser
from pathlib import Path

from . import analyze as analyze_mod
from . import download, report, separate


def _summarize(data):
    t, meta = data["tempo"], data["meta"]
    print()
    print(f"  {meta['title']}" + (f" — {meta['artist']}" if meta["artist"] else ""))
    print(f"  {t['bpm']:.0f} BPM · {data['key_guess']} · {t['stability']} · {t['swing']}")
    print(f"  {len(data['sections'])} sections · {t['beat_count']} beats")
    print()
    for name, st in data["stems"].items():
        bar = "▇" * round(st["coverage"] * 24)
        print(f"  {name:<7} {st['coverage'] * 100:>3.0f}% {bar}")
    print()


def _prepare_audio(args, out_root: Path):
    """Get source.mp3 + meta into a run directory named after the track."""
    staging = out_root / "_incoming"
    if staging.exists():
        shutil.rmtree(staging)

    if args.file:
        src = Path(args.file).expanduser()
        if not src.exists():
            sys.exit(f"no such file: {src}")
        print(f"[download] importing {src.name}…", flush=True)
        mp3, meta = download.import_local(src, staging)
    else:
        print(f"[download] fetching {args.target!r}…", flush=True)
        mp3, meta = download.fetch_youtube(args.target, staging)

    run_dir = out_root / download.slugify(meta["title"])
    run_dir.mkdir(parents=True, exist_ok=True)
    dest = run_dir / "source.mp3"
    shutil.move(str(mp3), dest)
    shutil.rmtree(staging, ignore_errors=True)
    return dest, meta, run_dir


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m layers", description=__doc__)
    ap.add_argument("target", nargs="?", help="YouTube URL, or a search phrase")
    ap.add_argument("--file", help="use a local audio file instead of downloading")
    ap.add_argument("--out", default="output", help="root output directory (default: output)")
    ap.add_argument("--start", type=float, help="analyse from this offset, in seconds")
    ap.add_argument("--duration", type=float, help="analyse only this many seconds")
    ap.add_argument("--report-only", metavar="RUN_DIR",
                    help="re-render report.html from an existing analysis.json")
    ap.add_argument("--no-open", action="store_true", help="don't open the report in a browser")
    args = ap.parse_args(argv)

    if args.report_only:
        run_dir = Path(args.report_only)
        data = json.loads((run_dir / "analysis.json").read_text())
        dest = report.render(data, run_dir)
        print(f"[report] {dest}")
        if not args.no_open:
            webbrowser.open(dest.resolve().as_uri())
        return

    if not args.target and not args.file:
        ap.error("give a URL / search phrase, or --file")

    out_root = Path(args.out)
    mp3, meta, run_dir = _prepare_audio(args, out_root)

    # A 44.1 kHz wav is what Demucs and librosa both want; it also does the
    # trimming, so the clip the player shows is exactly the clip analysed.
    print("[download] rendering analysis wav…", flush=True)
    wav = download.to_wav(mp3, run_dir / "analysis.wav", args.start, args.duration)
    if args.start or args.duration:
        download.to_mp3(wav, mp3)

    print("[separate] splitting into stems (first run downloads the model)…", flush=True)
    stems = separate.separate(wav, run_dir)

    data = analyze_mod.analyze(wav, stems, meta)
    (run_dir / "analysis.json").write_text(json.dumps(data, indent=1))

    dest = report.render(data, run_dir)
    wav.unlink(missing_ok=True)

    _summarize(data)
    print(f"  report → {dest}")
    if not args.no_open:
        webbrowser.open(dest.resolve().as_uri())


if __name__ == "__main__":
    main()
