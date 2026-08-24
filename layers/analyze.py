"""Musical analysis of the separated stems.

Everything downstream (report UI, console summary) reads the dict produced by
`analyze()`. All arrays are plain Python lists so it serializes straight to
JSON. Time signature is assumed 4/4 — true for the vast majority of popular
music, and the report states the assumption.
"""

import numpy as np
import librosa

SR = 22050
HOP = 512

KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _load(path):
    y, _ = librosa.load(str(path), sr=SR, mono=True)
    return y


def _frames_time(n):
    return librosa.frames_to_time(np.arange(n), sr=SR, hop_length=HOP)


def _resample_curve(curve, n_points, scale=100):
    """Downsample a positive curve to n_points ints in 0..scale (bucket max)."""
    if len(curve) == 0:
        return [0] * n_points
    peak = curve.max() or 1.0
    idx = np.linspace(0, len(curve), n_points + 1).astype(int)
    out = [int(round(float(curve[a:b].max() if b > a else 0) / peak * scale)) for a, b in zip(idx[:-1], idx[1:])]
    return out


def _peaks(y, n_points=800):
    return _resample_curve(np.abs(y), n_points)


def _band_env(M_db, freqs, lo, hi):
    mask = (freqs >= lo) & (freqs < hi)
    return librosa.onset.onset_strength(S=M_db[mask], sr=SR, hop_length=HOP)


def _onset_times(env, **kw):
    return librosa.onset.onset_detect(
        onset_envelope=env, sr=SR, hop_length=HOP, units="time", **kw
    )


def _activity(y, min_len=0.8, max_gap=0.6):
    """RMS-based activity: coverage fraction + merged [start, end] segments."""
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    if rms.max() < 1e-4:
        return 0.0, [], rms
    thresh = max(rms.max() * 0.06, 1e-4)
    active = rms > thresh
    times = _frames_time(len(rms))
    segs = []
    start = None
    for t, a in zip(times, active):
        if a and start is None:
            start = t
        elif not a and start is not None:
            segs.append([start, t])
            start = None
    if start is not None:
        segs.append([start, float(times[-1])])
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] < max_gap:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    merged = [[round(a, 2), round(b, 2)] for a, b in merged if b - a >= min_len]
    coverage = float(np.mean(active))
    return coverage, merged, rms


def _classify_timing(onsets, beats):
    """Bucket each onset by where it lands inside its beat: 1 / & / 16ths / loose."""
    counts = {"on": 0, "eighth": 0, "sixteenth": 0, "loose": 0}
    if len(beats) < 2:
        return counts
    for t in onsets:
        if t < beats[0] or t > beats[-1]:
            continue
        i = min(np.searchsorted(beats, t, side="right") - 1, len(beats) - 2)
        interval = beats[i + 1] - beats[i]
        ph = (t - beats[i]) / interval
        if ph < 0.10 or ph > 0.90:
            counts["on"] += 1
        elif abs(ph - 0.5) <= 0.10:
            counts["eighth"] += 1
        elif abs(ph - 0.25) <= 0.08 or abs(ph - 0.75) <= 0.08:
            counts["sixteenth"] += 1
        else:
            counts["loose"] += 1
    return counts


def _lock_pct(onsets, anchors, window=0.045):
    """Fraction of onsets landing within `window` seconds of any anchor time."""
    if len(onsets) == 0 or len(anchors) == 0:
        return None
    anchors = np.asarray(anchors)
    hits = sum(1 for t in onsets if np.min(np.abs(anchors - t)) <= window)
    return round(hits / len(onsets), 3)


def _band_split(y):
    """Fraction of spectral energy in low (<150 Hz), mid (150–2k), high (>2k)."""
    S = np.abs(librosa.stft(y, hop_length=HOP)) ** 2
    freqs = librosa.fft_frequencies(sr=SR)
    total = S.sum() or 1.0
    low = S[freqs < 150].sum() / total
    mid = S[(freqs >= 150) & (freqs < 2000)].sum() / total
    return {"low": round(float(low), 3), "mid": round(float(mid), 3), "high": round(float(1 - low - mid), 3)}


def _key_guess(y):
    chroma = librosa.feature.chroma_stft(y=y, sr=SR).mean(axis=1)
    best, best_r = None, -2
    for shift in range(12):
        rolled = np.roll(chroma, -shift)
        for profile, mode in ((KK_MAJOR, "major"), (KK_MINOR, "minor")):
            r = np.corrcoef(rolled, profile)[0, 1]
            if r > best_r:
                best_r, best = r, f"{NOTE_NAMES[shift]} {mode}"
    return best


def _drum_grid(envs, beats, phase):
    """Average kick/snare/hat onset strength on a 16-step grid across all bars."""
    downbeat_idx = list(range(phase, len(beats) - 4, 4))
    grid = {name: np.zeros(16) for name in envs}
    n_bars = 0
    times = _frames_time(len(next(iter(envs.values()))))
    for db in downbeat_idx:
        bar_beats = beats[db : db + 5]
        if len(bar_beats) < 5:
            continue
        n_bars += 1
        for step in range(16):
            beat_i, frac = divmod(step, 4)
            t = bar_beats[beat_i] + (frac / 4) * (bar_beats[beat_i + 1] - bar_beats[beat_i])
            f = np.searchsorted(times, t)
            for name, env in envs.items():
                lo, hi = max(0, f - 1), min(len(env), f + 2)
                grid[name][step] += env[lo:hi].max() if hi > lo else 0
    if n_bars == 0:
        return {name: [0] * 16 for name in envs}, 0
    out = {}
    for name, g in grid.items():
        g = g / n_bars
        peak = g.max() or 1.0
        out[name] = [round(float(v / peak), 2) for v in g]
    return out, n_bars


def _sections(stem_rms, mix, duration):
    """Boundary detection on per-second stem-energy + chroma features."""
    n_sec = max(int(duration), 4)
    feats = []
    for rms in stem_rms.values():
        idx = np.linspace(0, len(rms), n_sec + 1).astype(int)
        per_sec = np.array([rms[a:b].mean() if b > a else 0 for a, b in zip(idx[:-1], idx[1:])])
        feats.append(per_sec / (per_sec.max() or 1.0))
    chroma = librosa.feature.chroma_stft(y=mix, sr=SR, hop_length=HOP)
    idx = np.linspace(0, chroma.shape[1], n_sec + 1).astype(int)
    chroma_sec = np.array([
        chroma[:, a:b].mean(axis=1) if b > a else np.zeros(12) for a, b in zip(idx[:-1], idx[1:])
    ]).T
    X = np.vstack([np.array(feats) * 2.0, chroma_sec])  # weight energy changes higher
    k = int(np.clip(duration / 28, 3, 10))
    bounds = list(librosa.segment.agglomerative(X, k)) + [n_sec]
    # merge slivers
    merged = [bounds[0]]
    for b in bounds[1:]:
        if b - merged[-1] < 6 and b != n_sec:
            continue
        merged.append(b)

    stem_names = list(stem_rms.keys())
    sections, profiles = [], []
    for a, b in zip(merged[:-1], merged[1:]):
        profile = X[: len(stem_names) * 1, a:b].mean(axis=1) if b > a else np.zeros(len(stem_names))
        energy = float(profile.mean()) / 2.0
        active = [
            stem_names[i]
            for i in range(len(stem_names))
            if profile[i] / 2.0 > 0.18
        ]
        # letter by similarity to previously seen sections
        letter = None
        for prev_profile, prev_letter in profiles:
            denom = (np.linalg.norm(profile) * np.linalg.norm(prev_profile)) or 1.0
            if float(profile @ prev_profile) / denom > 0.94:
                letter = prev_letter
                break
        if letter is None:
            letter = chr(ord("A") + len({l for _, l in profiles}))
            profiles.append((profile, letter))
        sections.append({
            "start": float(a), "end": float(b), "letter": letter,
            "active": active,
            "energy": round(energy, 2),
        })
    return sections


def _describe(name, st, bpm, sync):
    """Rule-based plain-English description of what a stem is doing."""
    if st["coverage"] < 0.04:
        return "Essentially silent in this track — the separation found almost nothing here."
    cov = f"{round(st['coverage'] * 100)}%"
    t = st["timing"]
    total = sum(t.values()) or 1
    on = t["on"] / total
    eighth = t["eighth"] / total
    loose = t["loose"] / total
    parts = []
    if name == "drums":
        parts.append(f"The clock of the track — it defines the {round(bpm)} BPM grid everything else locks to.")
        parts.append("Read its bar pattern in the rhythm grid below: kick anchoring, snare answering, hats subdividing.")
    elif name == "bass":
        parts.append(f"The anchor: active {cov} of the track, living in the low end.")
        lock = sync.get("bass_kick_lock")
        if lock is not None:
            if lock > 0.6:
                parts.append(f"{round(lock * 100)}% of its notes land together with the kick drum — that kick-and-bass agreement is what musicians call 'the pocket'.")
            else:
                parts.append(f"Only {round(lock * 100)}% of its notes land with the kick — it moves independently, weaving around the drums rather than doubling them.")
    elif name == "vocals":
        parts.append(f"The voice: present {cov} of the track.")
        if loose > 0.4:
            parts.append("Its phrases float loosely around the grid — singers push and pull against the beat for expression; that rub is deliberate.")
        elif on > 0.5:
            parts.append("It lands squarely on the beat — a rhythmic, percussive delivery.")
    elif name == "other":
        parts.append(f"The color: harmony and everything melodic that isn't voice, bass or drums (chords, keys, guitars, synths). Present {cov} of the track.")
    if name != "vocals":
        if on > 0.6:
            parts.append(f"Timing: {round(on * 100)}% of its hits sit right on the beat — it reinforces the pulse.")
        elif eighth > 0.35:
            parts.append(f"Timing: {round(eighth * 100)}% of its hits land on the off-beats (the '&' between counts) — that push-pull against the pulse is what makes it groove.")
        elif loose > 0.45:
            parts.append("Timing: it plays freely around the grid rather than snapping to it.")
    d = st["density_per_beat"]
    if d is not None:
        if d > 1.5:
            parts.append(f"It's busy — about {d:.1f} hits per beat.")
        elif d < 0.4 and st["coverage"] > 0.2:
            parts.append("It's sparse — long notes or few hits; it creates space rather than filling it.")
    return " ".join(parts)


def analyze(mix_path, stem_paths, meta):
    print("[analyze] loading audio…", flush=True)
    mix = _load(mix_path)
    duration = len(mix) / SR
    stems = {name: _load(p) for name, p in stem_paths.items()}

    # ---- beat grid from the drums stem (fall back to the mix) ----
    print("[analyze] tracking beats…", flush=True)
    drums = stems["drums"]
    beat_src = drums if float(np.sqrt((drums**2).mean())) > 1e-3 else mix
    oenv = librosa.onset.onset_strength(y=beat_src, sr=SR, hop_length=HOP)
    tempo, beat_frames = librosa.beat.beat_track(
        onset_envelope=oenv, sr=SR, hop_length=HOP, trim=False
    )
    bpm = float(np.atleast_1d(tempo)[0])
    beats = librosa.frames_to_time(beat_frames, sr=SR, hop_length=HOP)

    # downbeat phase: which of the 4 beat offsets carries the most accent
    strengths = oenv[beat_frames] if len(beat_frames) else np.array([0.0])
    phase = int(np.argmax([strengths[p::4].mean() if len(strengths[p::4]) else 0 for p in range(4)]))

    ibi = np.diff(beats)
    drift = float(ibi.std() / ibi.mean()) if len(ibi) > 3 else 0.0
    stability = (
        "machine-steady" if drift < 0.03
        else "mostly steady" if drift < 0.07
        else "breathing (human timing or tempo changes)"
    )

    # ---- kick / snare / hat band envelopes from the drum stem ----
    M = librosa.feature.melspectrogram(y=drums, sr=SR, hop_length=HOP, n_mels=96)
    M_db = librosa.power_to_db(M)
    mel_freqs = librosa.filters.mel_frequencies(n_mels=96, fmax=SR / 2)
    kick_env = _band_env(M_db, mel_freqs, 20, 130)
    snare_env = _band_env(M_db, mel_freqs, 200, 1800)
    hat_env = _band_env(M_db, mel_freqs, 5500, SR / 2)
    kick_onsets = _onset_times(kick_env)
    drum_onsets = _onset_times(librosa.onset.onset_strength(y=drums, sr=SR, hop_length=HOP))

    grid, n_bars = _drum_grid(
        {"kick": kick_env, "snare": snare_env, "hat": hat_env}, beats, phase
    )

    # swing: where do the hats' off-beat hits actually land inside the beat?
    swing = "straight"
    hat_onsets = _onset_times(hat_env)
    if len(beats) > 2 and len(hat_onsets) > 8:
        phases = []
        for t in hat_onsets:
            if t < beats[0] or t > beats[-1]:
                continue
            i = min(np.searchsorted(beats, t, side="right") - 1, len(beats) - 2)
            ph = (t - beats[i]) / (beats[i + 1] - beats[i])
            if 0.35 < ph < 0.75:
                phases.append(ph)
        if len(phases) > 6:
            med = float(np.median(phases))
            if med >= 0.55:
                swing = f"swung — off-beats land late (~{med:.2f} of the beat), a shuffle feel"

    # ---- per-stem analysis ----
    print("[analyze] analyzing stems…", flush=True)
    stem_data = {}
    stem_rms = {}
    sync = {}
    for name, y in stems.items():
        coverage, segments, rms = _activity(y)
        stem_rms[name] = rms
        env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
        onsets = _onset_times(env, backtrack=False)
        active_time = sum(b - a for a, b in segments) or 1e-6
        timing = _classify_timing(onsets, beats)
        beats_in_active = max(active_time * bpm / 60, 1e-6)
        stem_data[name] = {
            "file": f"stems/{name}.mp3",
            "coverage": round(coverage, 3),
            "segments": segments,
            "onset_count": int(len(onsets)),
            "density_per_beat": round(len(onsets) / beats_in_active, 2) if len(onsets) else None,
            "timing": timing,
            "bands": _band_split(y) if coverage > 0.02 else {"low": 0, "mid": 0, "high": 0},
            "peaks": _peaks(y),
            "rms": _resample_curve(rms, 400),
        }
        if name == "bass":
            sync["bass_kick_lock"] = _lock_pct(onsets, kick_onsets)
        elif name in ("vocals", "other"):
            sync[f"{name}_drum_lock"] = _lock_pct(onsets, drum_onsets, window=0.05)

    for name in stem_data:
        stem_data[name]["description"] = _describe(name, stem_data[name], bpm, sync)

    # ---- structure + key ----
    print("[analyze] detecting sections + key…", flush=True)
    sections = _sections(stem_rms, mix, duration)
    key = _key_guess(mix)

    lock = sync.get("bass_kick_lock")
    sync["description"] = (
        f"The bass locks with the kick on {round(lock * 100)}% of its notes."
        if lock is not None else "No bass-kick relationship measurable in this track."
    )

    exercises = [
        f"Press play and count '1-2-3-4' out loud with the flashing beat counter at {round(bpm)} BPM. Keep counting until the downbeat ('1') feels inevitable.",
        "Solo the DRUMS. Watch the rhythm grid: find the kick's steps, then the snare's. Most grooves put the snare on counts 2 and 4 — the backbeat. Clap on 2 and 4 along with it.",
        "Now mute the drums but keep the BASS. Keep counting 1-2-3-4 — the pulse is still there, implied by the bass. This is how musicians keep time when no drummer is playing.",
        "Solo VOCALS + DRUMS. Notice where each vocal phrase begins: on the '1', just before it, or just after? Singers rarely start exactly on the downbeat.",
        "Play everything and follow the arrangement map. Try to predict each section change 2 bars before it happens — arrangers telegraph changes with fills and risers.",
    ]

    return {
        "meta": {
            "title": meta.get("title", ""),
            "artist": meta.get("artist", ""),
            "url": meta.get("url", ""),
            "duration": round(duration, 2),
            "mp3": "source.mp3",
        },
        "tempo": {
            "bpm": round(bpm, 1),
            "stability": stability,
            "swing": swing,
            "beat_count": int(len(beats)),
        },
        "beats": [round(float(b), 3) for b in beats],
        "downbeat_phase": phase,
        "key_guess": key,
        "stems": stem_data,
        "drum_grid": {"grid": grid, "bars_used": n_bars},
        "sections": sections,
        "sync": sync,
        "exercises": exercises,
    }
