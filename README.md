# toy-factory

Small self-contained toys. Right now: **layers** — take a piece of music apart and
listen to the parts.

## layers

Point it at a song. It downloads the audio, splits it into four stems with
[Demucs](https://github.com/adefossez/demucs), measures what each one is doing with
librosa, and writes a single HTML page where you can mute layers one at a time and
hear what each is holding up.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python -m layers --serve                     # paste links in a browser
```

That opens a local page where you drop in a YouTube link and watch it work —
fetch, separate, measure, render — then lands you on the finished report. Past
runs are listed there, so you can go back to anything you've taken apart.

The same thing from the terminal:

```bash
.venv/bin/python -m layers "portishead glory box"      # search YouTube
.venv/bin/python -m layers https://youtu.be/...        # or a direct URL
.venv/bin/python -m layers --file ~/Music/demo.wav     # or a local file
```

Useful flags:

| flag | what it does |
| --- | --- |
| `--serve [PORT]` | the browser front end, on 127.0.0.1 (default port 8721) |
| `--start S --duration S` | analyse a clip; the player gets the same clip |
| `--out DIR` | where runs land (default `output/`) |
| `--report-only RUN_DIR` | re-render `report.html` from a saved `analysis.json` |
| `--no-open` | don't open a browser |

Each run produces a directory you can open or move anywhere:

```
output/<track>/
├── report.html      ← open this
├── analysis.json    ← every number the page draws
├── source.mp3
└── stems/{drums,bass,vocals,other}.mp3
```

### What the report shows

- **Four layers** — a waveform and mute/solo per stem. Keys `1`–`4` toggle,
  `0` resets, `space` plays, `←`/`→` scrub. The four stems stay sample-aligned;
  muting swaps the audio out without stopping the clock.
- **Arrangement** — section boundaries from stem energy plus harmonic change.
  Repeated letters mean the section came back around. Click to jump.
- **The bar** — one bar of the drum pattern averaged across the track, split into
  kick / snare / hat by frequency band.
- **Per-layer detail** — how much of the track it plays, how many hits, where those
  hits sit relative to the beat, and how its energy splits across the spectrum.
- **Exercises** — listening tasks that use the player to confirm the analysis by ear.

### Caveats

Separation leaks: a piano can bleed into `vocals`, and on a track with no singing
the `vocals` stem is whatever else sounded voice-like. Tempo, key and section
boundaries are estimates — the key guess in particular is a best-fit chroma
correlation, and it cannot tell a major key from its relative minor. 4/4 is assumed.

First run downloads an ffmpeg binary (~30 MB) and the Demucs model (~80 MB), then
caches both. Separation uses Apple's MPS GPU when available and falls back to CPU.

### Layout

```
layers/
├── __main__.py   CLI, on top of pipeline.run()
├── serve.py      local web front end (stdlib http.server, no framework)
├── pipeline.py   the four stages in order, with a progress callback
├── download.py   yt-dlp + ffmpeg (fetch, import, transcode, trim)
├── separate.py   Demucs subprocess, MPS with a CPU fallback
├── analyze.py    beats, key, sections, drum grid, per-stem stats
└── report.py     the HTML page
```

The CLI and the server both call `pipeline.run()`, so there is one definition of
what deconstructing a track means; they differ only in where progress is drawn.
The server binds to localhost, serves each run's audio with HTTP range requests
so seeking works, and never reaches outside `output/`.

`playground/layers-of-music.jsx` is the companion piece: a hand-built React
explainer that synthesizes a six-layer loop in the browser, for hearing the same
ideas on audio simple enough to be unambiguous.
