"""A local page where you paste a YouTube link and get the deconstruction back.

Stdlib only, bound to localhost. The browser posts a link, a worker thread runs
the same pipeline the CLI runs, and the page polls for stage progress until the
report is ready — then sends you straight to it.
"""

import http.cookies
import json
import mimetypes
import secrets
import threading
import time
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import pipeline, report

JOBS = {}
JOBS_LOCK = threading.Lock()
OUT_ROOT = Path("output")

# Set when the server is reachable from outside this machine. A job costs real
# CPU and writes to disk, so an open link is not something to hand out.
TOKEN = None
COOKIE = "layers_key"

STAGE_LABELS = {
    "download": "Fetching audio",
    "prepare": "Rendering for analysis",
    "separate": "Separating stems",
    "analyze": "Measuring the layers",
    "report": "Building the page",
}

INDEX_CSS = """
.wrap { max-width: 780px; margin: 0 auto; }
form { margin: 34px 0 0; }
.field { display: flex; gap: 10px; flex-wrap: wrap; }
input[type=text] {
  flex: 1 1 340px; background: var(--panel); border: 1px solid var(--line); color: var(--ink);
  border-radius: 11px; padding: 15px 17px; font-family: inherit; font-size: 15px;
}
input[type=text]::placeholder { color: #6C7689; }
input[type=text]:focus { outline: none; border-color: #8FA6D9; background: var(--panel-2); }
input[type=number] {
  width: 92px; background: var(--panel); border: 1px solid var(--line); color: var(--ink);
  border-radius: 9px; padding: 9px 11px; font-family: 'JetBrains Mono', monospace; font-size: 13px;
}
button.go {
  background: var(--ink); color: var(--bg); border: none; border-radius: 11px;
  padding: 15px 26px; font-size: 15px; font-weight: 700; flex: none;
  transition: transform 0.15s, opacity 0.2s;
}
button.go:hover:not(:disabled) { transform: translateY(-1px); }
button.go:disabled { opacity: 0.45; cursor: default; }
.clip { display: flex; align-items: center; gap: 10px; margin-top: 14px; color: var(--dim); font-size: 13px; }
.clip label { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; }

.progress { margin-top: 34px; display: none; }
.progress.on { display: block; }
.bar { height: 5px; background: var(--panel-2); border-radius: 3px; overflow: hidden; }
.bar i { display: block; height: 100%; width: 0; background: #8FA6D9; transition: width 0.4s ease; }
.bar.err i { background: #C9563F; }
.stages { margin-top: 20px; display: flex; flex-direction: column; gap: 2px; }
.stg {
  display: grid; grid-template-columns: 22px 1fr auto; gap: 12px; align-items: center;
  padding: 9px 0; border-top: 1px solid var(--line); color: #55607A; font-size: 14px;
}
.stg .tick { font-family: 'JetBrains Mono', monospace; font-size: 12px; text-align: center; }
.stg.active { color: var(--ink); }
.stg.done { color: var(--dim); }
.stg.active .tick { color: #8FA6D9; }
.stg.done .tick { color: #8FBF7F; }
.stg .det { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--dim); }
.err {
  margin-top: 18px; background: rgba(201,86,63,0.10); border: 1px solid #C9563F;
  border-radius: 10px; padding: 14px 16px; font-size: 13.5px; line-height: 1.6;
}
.err b { display: block; margin-bottom: 5px; }
.err code { font-family: 'JetBrains Mono', monospace; font-size: 11.5px; color: #E8B4A6; word-break: break-all; }

.runs { margin-top: 60px; }
.runs h2 { font-size: 20px; margin: 0 0 4px; }
.run-list { display: flex; flex-direction: column; gap: 8px; margin-top: 18px; }
.run {
  display: flex; align-items: center; justify-content: space-between; gap: 14px;
  background: var(--panel); border: 1px solid var(--line); border-radius: 11px;
  padding: 14px 17px; text-decoration: none; color: var(--ink);
  transition: border-color 0.2s, transform 0.15s;
}
.run:hover { border-color: #55617A; transform: translateY(-1px); }
.run-name { font-weight: 600; font-size: 15px; }
.run-meta { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--dim); }
.empty { color: var(--dim); font-size: 14px; font-style: italic; font-family: 'Newsreader', serif; }
.note { margin-top: 44px; color: var(--dim); font-size: 13px; line-height: 1.7; border-top: 1px solid var(--line); padding-top: 20px; }
"""

INDEX_JS = """
const $ = (s) => document.querySelector(s);
const STAGES = __STAGES__;
let timer = null;

function paint(j) {
  const idx = STAGES.indexOf(j.stage);
  STAGES.forEach((s, i) => {
    const el = $('#stg-' + s);
    el.classList.toggle('done', j.stage === 'done' || (idx > -1 && i < idx));
    el.classList.toggle('active', i === idx);
    el.querySelector('.tick').textContent =
      (j.stage === 'done' || (idx > -1 && i < idx)) ? '✓' : (i === idx ? '›' : '·');
    if (i === idx) el.querySelector('.det').textContent = j.detail || '';
  });
  const per = 100 / STAGES.length;
  const overall = idx < 0 ? (j.stage === 'done' ? 100 : 0)
                          : per * idx + per * ((j.pct ?? 0) / 100);
  $('.bar i').style.width = Math.max(overall, 2) + '%';
}

async function poll(id) {
  const j = await (await fetch('/api/job/' + id)).json();
  paint(j);
  if (j.error) {
    clearInterval(timer);
    $('.bar').classList.add('err');
    $('#err').style.display = 'block';
    $('#err code').textContent = j.error;
    $('.go').disabled = false;
    $('.go').textContent = 'Deconstruct';
  } else if (j.stage === 'done') {
    clearInterval(timer);
    $('.go').textContent = 'Opening…';
    location.href = j.url;
  }
}

$('form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const target = $('#target').value.trim();
  if (!target) return;
  $('.go').disabled = true;
  $('.go').textContent = 'Working…';
  $('#err').style.display = 'none';
  $('.bar').classList.remove('err');
  $('.progress').classList.add('on');
  const body = {
    target,
    start: $('#start').value ? +$('#start').value : null,
    duration: $('#dur').value ? +$('#dur').value : null,
  };
  const r = await (await fetch('/api/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })).json();
  timer = setInterval(() => poll(r.job), 600);
});
"""


def _index_html():
    runs = []
    if OUT_ROOT.exists():
        for d in sorted(OUT_ROOT.iterdir(), key=lambda p: -p.stat().st_mtime):
            info = d / "analysis.json"
            if not (d / "report.html").exists() or not info.exists():
                continue
            try:
                meta = json.loads(info.read_text())
            except json.JSONDecodeError:
                continue
            runs.append((d.name, meta["meta"]["title"], meta["tempo"]["bpm"],
                         meta["key_guess"], meta["meta"]["duration"]))

    run_html = "".join(
        f'<a class="run" href="/runs/{slug}/report.html">'
        f'<span class="run-name">{title}</span>'
        f'<span class="run-meta">{bpm:.0f} BPM · {key} · {int(dur) // 60}:{int(dur) % 60:02d}</span>'
        f'</a>'
        for slug, title, bpm, key, dur in runs
    ) or '<p class="empty">Nothing taken apart yet.</p>'

    stages = "".join(
        f'<div class="stg" id="stg-{s}"><span class="tick">·</span>'
        f'<span>{STAGE_LABELS[s]}</span><span class="det"></span></div>'
        for s in pipeline.STAGES
    )
    js = INDEX_JS.replace("__STAGES__", json.dumps(pipeline.STAGES))

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Layers</title>
<style>{report.CSS}{INDEX_CSS}</style></head>
<body><div class="wrap">
<div class="eyebrow">Layers</div>
<h1>Take a track apart</h1>
<p class="lede">Paste a YouTube link and it comes back as four separated layers you can
mute one at a time, with the tempo, key, arrangement and groove measured. A search
phrase works too, as does a path to a file on this machine.</p>

<form>
  <div class="field">
    <input id="target" type="text" autofocus autocomplete="off"
           placeholder="https://youtube.com/watch?v=…  ·  or: portishead glory box">
    <button class="go" type="submit">Deconstruct</button>
  </div>
  <div class="clip">
    <label for="start">clip</label>
    <input id="start" type="number" min="0" step="1" placeholder="from">
    <input id="dur" type="number" min="1" step="1" placeholder="secs">
    <span>optional — analyse just part of it, which is much faster</span>
  </div>
</form>

<div class="progress">
  <div class="bar"><i></i></div>
  <div class="stages">{stages}</div>
  <div class="err" id="err" style="display:none"><b>That didn't work.</b><code></code></div>
</div>

<div class="runs">
  <h2>Already taken apart</h2>
  <div class="run-list">{run_html}</div>
</div>

<p class="note">Runs on your machine and nothing leaves it. The first separation
downloads the Demucs model (~80&nbsp;MB) and then caches it; after that a
three-minute track takes a minute or two, mostly separation. Long tracks are
slow — use the clip fields while you're trying things out.</p>
</div>
<script>{js}</script>
</body></html>
"""


def _busy():
    with JOBS_LOCK:
        return any(j["stage"] != "done" and not j["error"] for j in JOBS.values())


def _start_job(target, start, duration):
    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {"stage": "download", "detail": "starting", "pct": 0,
                        "error": None, "url": None, "started": time.time()}

    def on_event(stage, detail="", pct=None):
        with JOBS_LOCK:
            JOBS[job_id].update(stage=stage, detail=detail, pct=pct)

    def work():
        try:
            # a path that exists locally is treated as a file, not a search phrase
            as_path = Path(target).expanduser()
            is_file = as_path.exists() and as_path.is_file()
            _data, run_dir, _html = pipeline.run(
                target=None if is_file else target,
                file=str(as_path) if is_file else None,
                out_root=OUT_ROOT, start=start, duration=duration, on_event=on_event,
            )
            with JOBS_LOCK:
                JOBS[job_id].update(stage="done", pct=100,
                                    url=f"/runs/{run_dir.name}/report.html")
        except Exception as exc:
            traceback.print_exc()
            with JOBS_LOCK:
                JOBS[job_id]["error"] = f"{type(exc).__name__}: {exc}"

    threading.Thread(target=work, daemon=True).start()
    return job_id


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # the pipeline's own progress is the interesting output

    def _authorized(self):
        """No token means localhost-only use; with one, a cookie or ?k= is required."""
        if TOKEN is None:
            return True
        jar = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        if COOKIE in jar and secrets.compare_digest(jar[COOKIE].value, TOKEN):
            return True
        supplied = parse_qs(urlparse(self.path).query).get("k", [""])[0]
        return bool(supplied) and secrets.compare_digest(supplied, TOKEN)

    def _deny(self):
        self._send(
            "<!doctype html><meta charset=utf-8><title>Layers</title>"
            "<body style='background:#0F1218;color:#9AA3B2;font:15px system-ui;"
            "display:grid;place-items:center;height:100vh;margin:0'>"
            "<p>This link needs its key.</p>", code=403)

    def _send(self, body, ctype="text/html; charset=utf-8", code=200, extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj), "application/json", code)

    def do_GET(self):
        if not self._authorized():
            return self._deny()
        path = unquote(urlparse(self.path).path)

        if path == "/":
            # trade the ?k= for a cookie so the key stays out of later requests
            extra = {"Cache-Control": "no-store"}
            if TOKEN and COOKIE not in self.headers.get("Cookie", ""):
                extra["Set-Cookie"] = f"{COOKIE}={TOKEN}; Path=/; SameSite=Lax; Max-Age=604800"
            return self._send(_index_html(), extra=extra)

        if path.startswith("/api/job/"):
            with JOBS_LOCK:
                job = JOBS.get(path.rsplit("/", 1)[-1])
            return self._json(job, 200) if job else self._json({"error": "no such job"}, 404)

        if path.startswith("/runs/"):
            return self._serve_file(path[len("/runs/"):])

        self._send("<h1>404</h1>", code=404)

    def do_POST(self):
        if not self._authorized():
            return self._deny()
        if urlparse(self.path).path != "/api/run":
            return self._send("<h1>404</h1>", code=404)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or "{}")
        target = (body.get("target") or "").strip()
        if not target:
            return self._json({"error": "nothing to work on"}, 400)
        if _busy():
            return self._json({"error": "already working on a track — one at a time"}, 429)
        return self._json({"job": _start_job(target, body.get("start"), body.get("duration"))})

    def _serve_file(self, rel):
        """Serve a run's report and audio, with Range support so seeking works."""
        target = (OUT_ROOT / rel).resolve()
        root = OUT_ROOT.resolve()
        if root not in target.parents or not target.is_file():
            return self._send("<h1>404</h1>", code=404)

        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        size = target.stat().st_size
        rng = self.headers.get("Range")

        if rng and rng.startswith("bytes="):
            first, _, last = rng[6:].partition("-")
            start = int(first) if first else 0
            end = int(last) if last else size - 1
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            with target.open("rb") as fh:
                fh.seek(start)
                chunk = fh.read(end - start + 1)
            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(len(chunk)))
            self.end_headers()
            self.wfile.write(chunk)
            return

        self._send(target.read_bytes(), ctype,
                   extra={"Accept-Ranges": "bytes", "Cache-Control": "no-store"})


def serve(port=8721, out_root="output", open_browser=True, token=None):
    global OUT_ROOT, TOKEN
    OUT_ROOT = Path(out_root)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    TOKEN = token
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/" + (f"?k={token}" if token else "")
    print(f"  layers → {url}   (ctrl-c to stop)")
    if token:
        print("  a key is required — share the whole url, key included")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
