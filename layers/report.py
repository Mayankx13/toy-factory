"""Render the analysis dict into a single self-contained HTML report.

The page sits next to source.mp3 and stems/ so every audio reference is
relative — open report.html straight off disk, no server needed. Playback is
four <audio> elements started together rather than Web Audio, because
fetch()/decodeAudioData is blocked under file:// but media elements are not.
"""

import json
from pathlib import Path

# Colours and framing carried over from playground/layers-of-music.jsx so the
# generated report and the hand-built explainer read as one project.
STEM_UI = {
    "drums": ("#C9563F", "the clock", "Kick, snare and hats — the grid everything else locks to."),
    "bass": ("#E08A3C", "the anchor", "The low end: pitch and pulse at the same time."),
    "other": ("#E4C662", "the color", "Chords, keys, guitars, synths — the harmonic body."),
    "vocals": ("#5FC0BE", "the voice", "The line you follow, and the words."),
}
STEM_ORDER = ["vocals", "other", "bass", "drums"]

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@400;600&family=Newsreader:ital,opsz,wght@1,6..72,400&display=swap');

:root {
  --bg: #0F1218; --panel: #161B24; --panel-2: #1C2230;
  --line: #2A3242; --ink: #E8E6DF; --dim: #9AA3B2;
}
* , *::before, *::after { box-sizing: border-box; }
body {
  margin: 0; min-height: 100vh; color: var(--ink);
  background:
    radial-gradient(1100px 500px at 75% -10%, rgba(143,166,217,0.10), transparent 60%),
    radial-gradient(900px 500px at 10% 110%, rgba(201,86,63,0.08), transparent 60%),
    var(--bg);
  font-family: 'Space Grotesk', system-ui, sans-serif;
  padding: clamp(20px, 4vw, 56px) clamp(16px, 5vw, 72px) 80px;
}
button { font-family: inherit; cursor: pointer; color: inherit; }
button:focus-visible { outline: 2px solid #8FA6D9; outline-offset: 2px; }
a { color: #8FA6D9; }

.eyebrow {
  font-family: 'JetBrains Mono', monospace; font-size: 11px;
  letter-spacing: 0.22em; text-transform: uppercase; color: var(--dim); margin-bottom: 14px;
}
h1 { font-size: clamp(28px, 5vw, 52px); margin: 0 0 6px; letter-spacing: -0.02em; line-height: 1.05; }
.artist { font-family: 'Newsreader', serif; font-style: italic; color: var(--dim); font-size: 19px; margin: 0 0 4px; }
.src { font-size: 13px; color: var(--dim); word-break: break-all; }

.readout { display: flex; flex-wrap: wrap; gap: 28px; margin: 30px 0 36px; }
.ro-label { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--dim); }
.ro-value { font-family: 'JetBrains Mono', monospace; font-size: 15px; font-weight: 600; margin-top: 3px; }

section { margin-top: 56px; }
h2 { font-size: clamp(21px, 3vw, 30px); margin: 0 0 10px; letter-spacing: -0.01em; }
.lede { color: var(--dim); max-width: 640px; line-height: 1.6; margin: 0 0 22px; font-size: 14.5px; }

/* transport */
.transport {
  position: sticky; top: 0; z-index: 20; margin: 0 -8px;
  background: rgba(15,18,24,0.92); backdrop-filter: blur(10px);
  border: 1px solid var(--line); border-radius: 14px; padding: 16px 18px;
  display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
}
.play {
  width: 52px; height: 52px; flex: none; border-radius: 50%; border: 1px solid var(--line);
  background: var(--panel-2); font-size: 17px; display: grid; place-items: center;
  transition: transform 0.15s, border-color 0.2s;
}
.play:hover { transform: translateY(-1px); border-color: #8FA6D9; }
.clock { font-family: 'JetBrains Mono', monospace; font-size: 13px; color: var(--dim); flex: none; }
.scrub { flex: 1 1 260px; height: 34px; position: relative; cursor: pointer; }
.scrub-track { position: absolute; inset: 15px 0 auto; height: 4px; background: var(--line); border-radius: 2px; }
.scrub-fill { position: absolute; inset: 15px auto auto 0; height: 4px; background: #8FA6D9; border-radius: 2px; width: 0; }
.beats { display: flex; gap: 7px; flex: none; }
.beats i {
  width: 13px; height: 13px; border-radius: 50%; border: 1px solid var(--line); display: block;
  transition: background 0.08s, box-shadow 0.08s;
}
.beats i.on { background: #8FA6D9; box-shadow: 0 0 12px rgba(143,166,217,0.7); }
.beats i.one.on { background: #C9563F; box-shadow: 0 0 14px rgba(201,86,63,0.8); }
.bar-count { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--dim); flex: none; min-width: 76px; }

/* stem rack */
.rack { display: flex; flex-direction: column; gap: 10px; }
.stem {
  background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px;
  display: grid; grid-template-columns: 190px 1fr auto; gap: 16px; align-items: center;
  transition: border-color 0.2s, opacity 0.2s;
}
.stem.silent { opacity: 0.42; }
.s-id { display: flex; align-items: center; gap: 10px; min-width: 0; }
.dot { width: 12px; height: 12px; border-radius: 3px; flex: none; border: 1px solid; }
.s-name { font-weight: 700; font-size: 15px; }
.s-tag { font-family: 'Newsreader', serif; font-style: italic; font-size: 13px; color: var(--dim); }
.wave-wrap { position: relative; min-width: 0; }
.wave-wrap::after {
  content: ''; position: absolute; top: 0; bottom: 0; left: var(--frac, 0%);
  width: 1px; background: var(--ink); opacity: 0.75; pointer-events: none;
}
.wave { width: 100%; height: 54px; display: block; cursor: pointer; border-radius: 6px; }
.s-ctrl { display: flex; gap: 6px; flex: none; }
.s-ctrl button {
  font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.08em;
  background: transparent; border: 1px solid var(--line); border-radius: 7px; padding: 7px 11px;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.s-ctrl button:hover { border-color: #55617A; }
.s-ctrl button.on { background: var(--ink); color: var(--bg); border-color: var(--ink); }
.s-ctrl button.solo.on { background: #E4C662; border-color: #E4C662; }

/* arrangement */
.map { display: flex; gap: 3px; height: 74px; margin-bottom: 10px; }
.sec {
  flex: 1 1 auto; background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  padding: 8px; display: flex; flex-direction: column; justify-content: space-between;
  cursor: pointer; overflow: hidden; transition: border-color 0.2s, background 0.2s;
  position: relative; min-width: 0;
}
.sec:hover { border-color: #55617A; }
.sec.now { border-color: var(--ink); background: var(--panel-2); }
.sec-letter { font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 13px; }
.sec-stems { display: flex; gap: 3px; }
.sec-stems i { width: 7px; height: 7px; border-radius: 2px; display: block; }
.sec-energy { position: absolute; left: 0; bottom: 0; height: 3px; background: #8FA6D9; opacity: 0.55; }
.map-time { display: flex; justify-content: space-between; font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--dim); }

/* drum grid */
.grid-wrap { overflow-x: auto; }
.grid-row { display: grid; grid-template-columns: 62px repeat(16, minmax(26px, 1fr)); gap: 4px; align-items: center; margin-bottom: 5px; }
.grid-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--dim); }
.cell { height: 26px; border-radius: 5px; border: 1px solid var(--line); background: var(--panel); }
.cell.beat1 { border-color: #3A465C; }
.step-nums { display: grid; grid-template-columns: 62px repeat(16, minmax(26px, 1fr)); gap: 4px; margin-top: 6px; }
.step-nums span { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--dim); text-align: center; }
.step-nums span.strong { color: var(--ink); }
.cell.playing { box-shadow: 0 0 0 1px var(--ink) inset; }

/* detail cards */
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 18px; }
.card h3 { margin: 0 0 4px; font-size: 17px; display: flex; align-items: center; gap: 9px; }
.card .s-tag { display: block; margin-bottom: 12px; }
.desc { font-size: 13.5px; line-height: 1.65; color: #B9BFCB; margin: 0 0 16px; }
.stat { display: flex; justify-content: space-between; font-family: 'JetBrains Mono', monospace; font-size: 11px; padding: 5px 0; border-top: 1px solid var(--line); }
.stat span:last-child { color: var(--dim); }
.meter { display: flex; height: 7px; border-radius: 4px; overflow: hidden; margin: 12px 0 6px; background: var(--panel-2); }
.meter i { display: block; height: 100%; }
.meter-key { display: flex; gap: 12px; font-family: 'JetBrains Mono', monospace; font-size: 9.5px; color: var(--dim); letter-spacing: 0.06em; }
.meter-key b { color: var(--ink); font-weight: 600; }

/* exercises */
ol.ex { counter-reset: e; list-style: none; padding: 0; margin: 0; max-width: 760px; }
ol.ex li {
  counter-increment: e; position: relative; padding: 16px 0 16px 52px;
  border-top: 1px solid var(--line); line-height: 1.65; font-size: 14.5px; color: #C6CBD5;
}
ol.ex li::before {
  content: counter(e, decimal-leading-zero); position: absolute; left: 0; top: 16px;
  font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #8FA6D9;
}
.foot { margin-top: 64px; border-top: 1px solid var(--line); padding-top: 26px; max-width: 720px; }
.foot p { color: var(--dim); line-height: 1.7; font-size: 13.5px; margin: 0 0 10px; }
kbd {
  font-family: 'JetBrains Mono', monospace; font-size: 11px; background: var(--panel-2);
  border: 1px solid var(--line); border-bottom-width: 2px; border-radius: 5px; padding: 1px 6px;
}
@media (max-width: 800px) {
  .stem { grid-template-columns: 1fr; }
  .s-ctrl { justify-content: flex-start; }
  .map { height: 96px; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
"""

JS = """
const D = window.__LAYERS__;
const ORDER = window.__ORDER__;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

/* ---- audio: one element per stem, started together ---- */
const els = {};
ORDER.forEach((name) => { els[name] = $('audio[data-stem="' + name + '"]'); });
const master = els[ORDER[ORDER.length - 1]];   // drums: the longest-lived reference
const muted = new Set();
let soloed = null;
let playing = false;

function applyGains() {
  ORDER.forEach((name) => {
    const audible = soloed ? soloed === name : !muted.has(name);
    els[name].muted = !audible;
    $('.stem[data-stem="' + name + '"]').classList.toggle('silent', !audible);
    $('.s-ctrl button.mute[data-stem="' + name + '"]').classList.toggle('on', muted.has(name));
    $('.s-ctrl button.solo[data-stem="' + name + '"]').classList.toggle('on', soloed === name);
  });
}

function seek(t) {
  t = Math.max(0, Math.min(t, D.meta.duration));
  ORDER.forEach((name) => { els[name].currentTime = t; });
  draw();
}

async function toggle() {
  if (playing) {
    ORDER.forEach((n) => els[n].pause());
    playing = false;
  } else {
    const t = master.currentTime;
    ORDER.forEach((n) => { els[n].currentTime = t; });
    await Promise.all(ORDER.map((n) => els[n].play()));
    playing = true;
  }
  $('.play').textContent = playing ? '❚❚' : '▶';
}

/* Media elements drift apart over minutes; nudge strays back to the master. */
setInterval(() => {
  if (!playing) return;
  const t = master.currentTime;
  ORDER.forEach((n) => {
    if (n !== ORDER[ORDER.length - 1] && Math.abs(els[n].currentTime - t) > 0.06) els[n].currentTime = t;
  });
}, 1000);

/* ---- waveforms ---- */
function paintWave(name) {
  const cv = $('canvas[data-stem="' + name + '"]');
  const peaks = D.stems[name].peaks;
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  cv.width = w * dpr; cv.height = h * dpr;
  const c = cv.getContext('2d');
  c.scale(dpr, dpr);
  c.clearRect(0, 0, w, h);
  const bw = w / peaks.length;
  c.fillStyle = D.stems[name].color;
  peaks.forEach((p, i) => {
    const bh = Math.max(1, (p / 100) * (h - 2));
    c.globalAlpha = 0.30 + 0.55 * (p / 100);
    c.fillRect(i * bw, (h - bh) / 2, Math.max(bw - 0.5, 0.6), bh);
  });
  c.globalAlpha = 1;
}

/* ---- beat + bar readout ---- */
function beatAt(t) {
  const b = D.beats;
  if (!b.length) return -1;
  let lo = 0, hi = b.length - 1, idx = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (b[mid] <= t) { idx = mid; lo = mid + 1; } else { hi = mid - 1; }
  }
  return idx;
}

/* ---- per-frame paint ---- */
function draw() {
  const t = master.currentTime;
  const dur = D.meta.duration || 1;

  $('.clock').textContent = fmt(t) + ' / ' + fmt(dur);
  $('.scrub-fill').style.width = (t / dur * 100) + '%';

  const bi = beatAt(t);
  const inBar = bi < 0 ? -1 : ((bi - D.downbeat_phase) % 4 + 4) % 4;
  $$('.beats i').forEach((el, i) => el.classList.toggle('on', i === inBar));
  $('.bar-count').textContent = bi < 0 ? 'bar —' : 'bar ' + (Math.floor((bi - D.downbeat_phase) / 4) + 1);

  // step within the bar drives the drum-grid highlight
  let step = -1;
  if (bi >= 0 && bi + 1 < D.beats.length && inBar >= 0) {
    const frac = (t - D.beats[bi]) / (D.beats[bi + 1] - D.beats[bi]);
    step = inBar * 4 + Math.min(3, Math.floor(frac * 4));
  }
  $$('.cell').forEach((c) => c.classList.toggle('playing', +c.dataset.step === step));

  $$('.sec').forEach((s) => s.classList.toggle('now', t >= +s.dataset.start && t < +s.dataset.end));

  // playhead line over each waveform
  $$('.wave-wrap').forEach((w) => { w.style.setProperty('--frac', (t / dur * 100) + '%'); });

  if (playing) requestAnimationFrame(draw);
}

function fmt(s) {
  s = Math.max(0, Math.floor(s));
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

/* ---- wiring ---- */
$('.play').addEventListener('click', async () => { await toggle(); if (playing) draw(); });
master.addEventListener('ended', () => { playing = false; $('.play').textContent = '▶'; });

$('.scrub').addEventListener('click', (e) => {
  const r = e.currentTarget.getBoundingClientRect();
  seek((e.clientX - r.left) / r.width * D.meta.duration);
});

$$('.wave').forEach((cv) => {
  cv.addEventListener('click', (e) => {
    const r = cv.getBoundingClientRect();
    seek((e.clientX - r.left) / r.width * D.meta.duration);
  });
});

$$('.s-ctrl button.mute').forEach((b) => b.addEventListener('click', () => {
  const n = b.dataset.stem;
  muted.has(n) ? muted.delete(n) : muted.add(n);
  if (soloed) soloed = null;
  applyGains();
}));
$$('.s-ctrl button.solo').forEach((b) => b.addEventListener('click', () => {
  const n = b.dataset.stem;
  soloed = soloed === n ? null : n;
  applyGains();
}));

$$('.sec').forEach((s) => s.addEventListener('click', () => seek(+s.dataset.start)));

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') return;
  if (e.code === 'Space') { e.preventDefault(); $('.play').click(); }
  const i = '1234'.indexOf(e.key);
  if (i >= 0 && i < ORDER.length) {
    const n = ORDER[i];
    muted.has(n) ? muted.delete(n) : muted.add(n);
    soloed = null;
    applyGains();
  }
  if (e.key === '0') { muted.clear(); soloed = null; applyGains(); }
  if (e.key === 'ArrowLeft') seek(master.currentTime - 5);
  if (e.key === 'ArrowRight') seek(master.currentTime + 5);
});

window.addEventListener('resize', () => ORDER.forEach(paintWave));
ORDER.forEach(paintWave);
applyGains();
draw();
"""


def _stat(label, value):
    return f'<div class="stat"><span>{label}</span><span>{value}</span></div>'


def _stem_card(name, st):
    color, tag, _blurb = STEM_UI[name]
    t = st["timing"]
    total = sum(t.values()) or 1
    bands = st["bands"]
    meter = (
        f'<div class="meter">'
        f'<i style="width:{bands["low"] * 100:.1f}%;background:#E08A3C"></i>'
        f'<i style="width:{bands["mid"] * 100:.1f}%;background:#E4C662"></i>'
        f'<i style="width:{bands["high"] * 100:.1f}%;background:#5FC0BE"></i>'
        f'</div>'
        f'<div class="meter-key">'
        f'<span><b>{bands["low"] * 100:.0f}%</b> low</span>'
        f'<span><b>{bands["mid"] * 100:.0f}%</b> mid</span>'
        f'<span><b>{bands["high"] * 100:.0f}%</b> high</span>'
        f'</div>'
    )
    density = "—" if st["density_per_beat"] is None else f'{st["density_per_beat"]:.2f}/beat'
    stats = "".join([
        _stat("active", f'{st["coverage"] * 100:.0f}% of track'),
        _stat("hits", f'{st["onset_count"]}'),
        _stat("density", density),
        _stat("on the beat", f'{t["on"] / total * 100:.0f}%'),
        _stat("off-beat (&)", f'{t["eighth"] / total * 100:.0f}%'),
        _stat("16ths", f'{t["sixteenth"] / total * 100:.0f}%'),
        _stat("loose", f'{t["loose"] / total * 100:.0f}%'),
    ])
    return (
        f'<div class="card">'
        f'<h3><i class="dot" style="background:{color};border-color:{color}"></i>{name.title()}</h3>'
        f'<span class="s-tag">{tag}</span>'
        f'<p class="desc">{st["description"]}</p>'
        f'{meter}{stats}</div>'
    )


def _stem_row(name, st):
    color, tag, blurb = STEM_UI[name]
    return (
        f'<div class="stem" data-stem="{name}">'
        f'<div class="s-id">'
        f'<i class="dot" style="background:{color};border-color:{color}"></i>'
        f'<div><div class="s-name">{name.title()}</div><div class="s-tag">{tag}</div></div>'
        f'</div>'
        f'<div class="wave-wrap" title="{blurb}"><canvas class="wave" data-stem="{name}"></canvas></div>'
        f'<div class="s-ctrl">'
        f'<button class="mute" data-stem="{name}">MUTE</button>'
        f'<button class="solo" data-stem="{name}">SOLO</button>'
        f'</div></div>'
    )


def _sections_html(sections):
    out = []
    for s in sections:
        span = max(s["end"] - s["start"], 0.5)
        dots = "".join(
            f'<i style="background:{STEM_UI[n][0]}"></i>' for n in STEM_ORDER if n in s["active"]
        )
        out.append(
            f'<div class="sec" data-start="{s["start"]}" data-end="{s["end"]}" '
            f'style="flex-grow:{span}" title="{s["start"]:.0f}s – {s["end"]:.0f}s">'
            f'<div class="sec-letter">{s["letter"]}</div>'
            f'<div class="sec-stems">{dots}</div>'
            f'<div class="sec-energy" style="width:{min(s["energy"], 1) * 100:.0f}%"></div>'
            f'</div>'
        )
    return "".join(out)


def _grid_html(drum_grid):
    grid = drum_grid["grid"]
    rows = []
    colors = {"kick": "#C9563F", "snare": "#E08A3C", "hat": "#E4C662"}
    for part in ("kick", "snare", "hat"):
        cells = []
        for step, v in enumerate(grid.get(part, [0] * 16)):
            beat1 = " beat1" if step % 4 == 0 else ""
            bg = (
                f'background:{colors[part]};opacity:{0.15 + 0.85 * v:.2f}'
                if v > 0.18 else ""
            )
            cells.append(f'<div class="cell{beat1}" data-step="{step}" style="{bg}"></div>')
        rows.append(
            f'<div class="grid-row"><div class="grid-label">{part}</div>{"".join(cells)}</div>'
        )
    nums = "".join(
        f'<span class="{"strong" if i % 4 == 0 else ""}">{i // 4 + 1 if i % 4 == 0 else "·"}</span>'
        for i in range(16)
    )
    rows.append(f'<div class="step-nums"><span></span>{nums}</div>')
    return "".join(rows)


def render(data, out_dir: Path) -> Path:
    """Write report.html into out_dir (next to source.mp3 and stems/)."""
    out_dir = Path(out_dir)
    meta, tempo = data["meta"], data["tempo"]
    stems = data["stems"]

    for name in stems:
        stems[name]["color"] = STEM_UI[name][0]

    order = [n for n in STEM_ORDER if n in stems]
    audio = "".join(
        f'<audio data-stem="{n}" src="{stems[n]["file"]}" preload="auto"></audio>' for n in order
    )
    readout = "".join(
        f'<div><div class="ro-label">{label}</div><div class="ro-value">{value}</div></div>'
        for label, value in [
            ("tempo", f'{tempo["bpm"]:.0f} BPM'),
            ("key (est.)", data["key_guess"]),
            ("length", f'{int(meta["duration"]) // 60}:{int(meta["duration"]) % 60:02d}'),
            ("pulse", tempo["stability"]),
            ("feel", tempo["swing"]),
            ("sections", str(len(data["sections"]))),
        ]
    )
    # a local import puts a filesystem path in meta.url — show it, don't linkify it
    url = meta.get("url", "")
    if url.startswith(("http://", "https://")):
        src_line = f'<div class="src"><a href="{url}">{url}</a></div>'
    elif url:
        src_line = f'<div class="src">{Path(url).name}</div>'
    else:
        src_line = ""
    payload = json.dumps(data).replace("</", "<\\/")

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{meta["title"]} — layers</title>
<style>{CSS}</style></head>
<body>
{audio}
<div class="eyebrow">Layers · a track taken apart</div>
<h1>{meta["title"]}</h1>
<p class="artist">{meta["artist"] or "unknown artist"}</p>
{src_line}
<div class="readout">{readout}</div>

<div class="transport">
  <button class="play" aria-label="play or pause">▶</button>
  <div class="clock">0:00 / 0:00</div>
  <div class="scrub"><div class="scrub-track"></div><div class="scrub-fill"></div></div>
  <div class="beats"><i class="one"></i><i></i><i></i><i></i></div>
  <div class="bar-count">bar —</div>
</div>

<section>
  <h2>The four layers</h2>
  <p class="lede">Demucs pulled these apart from the finished mix. Mute one and listen to
  what its absence does — that gap is the clearest description of its job. Keys
  <kbd>1</kbd>–<kbd>4</kbd> toggle, <kbd>0</kbd> resets, <kbd>space</kbd> plays.</p>
  <div class="rack">{"".join(_stem_row(n, stems[n]) for n in order)}</div>
</section>

<section>
  <h2>Arrangement</h2>
  <p class="lede">Boundaries found by watching stem energy and harmony shift together.
  Letters mark sections that resemble each other — the same letter twice is a repeat
  (a chorus coming back around). Dots show which layers are playing. Click to jump.</p>
  <div class="map">{_sections_html(data["sections"])}</div>
  <div class="map-time"><span>0:00</span><span>{int(meta["duration"]) // 60}:{int(meta["duration"]) % 60:02d}</span></div>
</section>

<section>
  <h2>The bar</h2>
  <p class="lede">One bar of the drum pattern, averaged over {data["drum_grid"]["bars_used"]} bars
  and split by frequency: kick low, snare mid, hats high. Brightness is how hard that step
  is hit. Assumes 4/4 — sixteen steps, four to a beat.</p>
  <div class="grid-wrap">{_grid_html(data["drum_grid"])}</div>
</section>

<section>
  <h2>What each layer is doing</h2>
  <p class="lede">{data["sync"]["description"]}</p>
  <div class="cards">{"".join(_stem_card(n, stems[n]) for n in order)}</div>
</section>

<section>
  <h2>Try this</h2>
  <p class="lede">The analysis above is only useful once your ears confirm it. Work through
  these with the player.</p>
  <ol class="ex">{"".join(f"<li>{e}</li>" for e in data["exercises"])}</ol>
</section>

<div class="foot">
  <p>Stems separated with Demucs (htdemucs), analysis with librosa. Tempo, key, sections and
  the drum grid are estimates — separation leaks, and a key guess from chroma is a best fit,
  not a fact. Time signature is assumed 4/4.</p>
  <p>Everything here is derived from your own copy of the audio and stays on this machine.</p>
</div>

<script>window.__LAYERS__ = {payload}; window.__ORDER__ = {json.dumps(order)};</script>
<script>{JS}</script>
</body></html>
"""
    dest = out_dir / "report.html"
    dest.write_text(html, encoding="utf-8")
    return dest
