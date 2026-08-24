"""Command line entry point: a URL or a file in, a playable report out.

    python -m layers --serve                        # paste links in a browser
    python -m layers "aphex twin xtal"
    python -m layers https://youtu.be/... --start 30 --duration 60
    python -m layers --file ~/Music/demo.wav
    python -m layers --report-only output/xtal      # re-render, skip the slow parts
"""

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from . import pipeline, report, serve

_progress_open = False


def _console(stage, detail="", pct=None):
    """Mirror pipeline events to the terminal, keeping percentages on one line."""
    global _progress_open
    if stage == "done":
        if _progress_open:
            print()
        _progress_open = False
        return
    if pct is None:
        if _progress_open:
            print()
            _progress_open = False
        print(f"[{stage}] {detail}", flush=True)
    else:
        print(f"\r[{stage}] {detail} {pct:3.0f}%".ljust(64), end="", flush=True)
        _progress_open = True


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


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m layers", description=__doc__)
    ap.add_argument("target", nargs="?", help="YouTube URL, or a search phrase")
    ap.add_argument("--serve", nargs="?", const=8721, type=int, metavar="PORT",
                    help="open a local page for pasting links (default port 8721)")
    ap.add_argument("--file", help="use a local audio file instead of downloading")
    ap.add_argument("--out", default="output", help="root output directory (default: output)")
    ap.add_argument("--start", type=float, help="analyse from this offset, in seconds")
    ap.add_argument("--duration", type=float, help="analyse only this many seconds")
    ap.add_argument("--report-only", metavar="RUN_DIR",
                    help="re-render report.html from an existing analysis.json")
    ap.add_argument("--no-open", action="store_true", help="don't open a browser")
    args = ap.parse_args(argv)

    if args.serve:
        return serve.serve(port=args.serve, out_root=args.out, open_browser=not args.no_open)

    if args.report_only:
        run_dir = Path(args.report_only)
        data = json.loads((run_dir / "analysis.json").read_text())
        dest = report.render(data, run_dir)
        print(f"[report] {dest}")
        if not args.no_open:
            webbrowser.open(dest.resolve().as_uri())
        return

    if not args.target and not args.file:
        ap.error("give a URL / search phrase, --file, or --serve")

    try:
        data, _run_dir, dest = pipeline.run(
            target=args.target, file=args.file, out_root=args.out,
            start=args.start, duration=args.duration, on_event=_console,
        )
    except FileNotFoundError as exc:
        sys.exit(str(exc))

    _summarize(data)
    print(f"  report → {dest}")
    if not args.no_open:
        webbrowser.open(dest.resolve().as_uri())


if __name__ == "__main__":
    main()
