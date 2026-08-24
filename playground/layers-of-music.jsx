import React, { useState, useRef, useEffect, useCallback } from "react";
import * as Tone from "tone";

/* ------------------------------------------------------------------ */
/*  Musical data — a 4-bar loop in A minor (Am → F → C → G)           */
/* ------------------------------------------------------------------ */

const CHORDS = [
  { name: "A minor", bass: ["A1", "E2", "A2"], stab: ["A3", "C4", "E4"], pad: ["A2", "E3", "A3", "C4"] },
  { name: "F major", bass: ["F1", "C2", "F2"], stab: ["F3", "A3", "C4"], pad: ["F2", "C3", "F3", "A3"] },
  { name: "C major", bass: ["C2", "G2", "C3"], stab: ["E3", "G3", "C4"], pad: ["C3", "G3", "C4", "E4"] },
  { name: "G major", bass: ["G1", "D2", "G2"], stab: ["G3", "B3", "D4"], pad: ["G2", "D3", "G3", "B3"] },
];

const KICK = [0, 8, 10];
const SNARE = [4, 12];
const OPEN_HAT = [14];
const BASS_STEPS = [0, 3, 6, 8, 11, 14];
const BASS_NOTE_IDX = [0, 0, 1, 0, 2, 1]; // root, root, fifth, root, octave, fifth
const STAB_STEPS = [0, 7, 10];

const MELODY = [
  { 0: "A4", 2: "C5", 4: "E5", 7: "D5", 10: "C5", 12: "A4" },
  { 0: "C5", 3: "A4", 6: "G4", 8: "A4", 12: "C5", 14: "D5" },
  { 0: "E5", 2: "G5", 4: "E5", 8: "D5", 10: "C5", 14: "D5" },
  { 0: "B4", 4: "D5", 6: "B4", 8: "A4", 10: "G4", 12: "A4" },
];

const COUNTER = [
  { 6: "E4", 14: "G4" },
  { 6: "F4", 14: "E4" },
  { 6: "G4", 13: "A4" },
  { 6: "D4", 12: "B3" },
];

/* ------------------------------------------------------------------ */
/*  Layer metadata — ordered high frequencies → low (like a mix)      */
/* ------------------------------------------------------------------ */

const LAYERS = [
  {
    id: "texture",
    name: "Texture / Pad",
    tag: "the air",
    color: "#8FA6D9",
    freq: "2–12 kHz sheen",
    role: "Sustained sound that fills the space between everything else's attacks. It has no rhythm and no tune of its own — its job is atmosphere and glue.",
    listen: "A held chord that changes once per bar, sitting behind the mix like fog.",
    without: "Mute it and the track suddenly feels dry and small. Nothing is 'missing', exactly — but the room got smaller.",
    examples: "String pads, organ, choir 'aahs', synth washes, long reverb tails.",
  },
  {
    id: "melody",
    name: "Melody",
    tag: "the voice",
    color: "#5FC0BE",
    freq: "300 Hz – 2 kHz lead",
    role: "The foreground line — the part you'd hum. A melody is a sequence of pitches with its own rhythm and shape (contour), and it sits on top of everything else.",
    listen: "The highest, most active tune. Notice it rises to its peak in bar 3, then settles back down — that arc is deliberate.",
    without: "Mute it and you're left with a backing track. Everything still works, but there's nothing to follow.",
    examples: "A singer's vocal, a violin theme, a guitar solo, a whistled hook.",
  },
  {
    id: "counter",
    name: "Counter-melody",
    tag: "the reply",
    color: "#8FBF7F",
    freq: "200 Hz – 1 kHz second line",
    role: "A second, independent tune that answers the main melody — deliberately placed in its gaps, so the two lines talk rather than collide.",
    listen: "Solo it with the melody: every counter note lands where the melody breathes. That call-and-response is the craft.",
    without: "Mute it and nothing breaks — but the arrangement loses its conversation and feels more one-dimensional.",
    examples: "Horn stabs behind a vocal, backing-vocal riffs, the interweaving lines of a Bach fugue.",
  },
  {
    id: "harmony",
    name: "Harmony",
    tag: "the color",
    color: "#E4C662",
    freq: "150 Hz – 1 kHz body",
    role: "Chords — several notes at once — that give the melody emotional context. The same melody note feels bright over one chord and melancholy over another.",
    listen: "Short rhythmic chord stabs. This loop cycles Am → F → C → G; feel how bar 1 is wistful and bar 3 opens up, even though the drums never change.",
    without: "Mute it (and the pad) and the melody becomes ambiguous — your ear can no longer tell if the music is 'sad' or 'bright'.",
    examples: "Piano comping, strummed guitar, a string section, synth stabs.",
  },
  {
    id: "bass",
    name: "Bass",
    tag: "the anchor",
    color: "#E08A3C",
    freq: "40–250 Hz foundation",
    role: "The bridge between rhythm and harmony. It plays the lowest notes — mostly chord roots — but phrases them as a groove that locks with the kick drum.",
    listen: "How the bassline lands with the kick on beat 1, then walks up to the octave. It's playing the harmony and the rhythm at once.",
    without: "Mute it and the mix goes weightless. The chords also become vaguer — the bass note tells your ear which chord you're on.",
    examples: "Electric bass, upright bass, 808 sub, left hand of a piano.",
  },
  {
    id: "drums",
    name: "Rhythm / Drums",
    tag: "the clock",
    color: "#C9563F",
    freq: "Full spectrum pulse",
    role: "The timekeeper. Kick and snare mark the beat, hi-hats subdivide it into a grid — together they define the tempo and the groove everything else locks to.",
    listen: "Kick anchoring the downbeats, snare cracking the backbeat (beats 2 & 4), hats ticking eighth-notes with an open hat pushing into the next bar.",
    without: "Mute it and time doesn't disappear — the bass still implies it — but the momentum and physical drive drop instantly.",
    examples: "Drum kit, drum machine, tabla, hand claps, a stomping foot.",
  },
];

/* Which cells light up in each layer's step grid */
function layerHits(id, bar) {
  const set = new Set();
  if (id === "drums") for (let i = 0; i < 16; i += 2) set.add(i);
  if (id === "bass") BASS_STEPS.forEach((s) => set.add(s));
  if (id === "harmony") STAB_STEPS.forEach((s) => set.add(s));
  if (id === "melody") Object.keys(MELODY[bar]).forEach((s) => set.add(+s));
  if (id === "counter") Object.keys(COUNTER[bar]).forEach((s) => set.add(+s));
  if (id === "texture") set.add(0);
  return set;
}

/* ------------------------------------------------------------------ */
/*  Texture presets — mute configs that double as a mini music lesson */
/* ------------------------------------------------------------------ */

const PRESETS = [
  {
    id: "mono",
    name: "Monophony",
    sub: "one voice alone",
    on: ["melody"],
    desc: "A single unaccompanied line. Chant, a solo flute, someone humming. The oldest texture in music.",
  },
  {
    id: "homo",
    name: "Homophony",
    sub: "melody + accompaniment",
    on: ["melody", "harmony", "bass"],
    desc: "One lead line supported by chords underneath — how nearly all pop, folk and hymns are built.",
  },
  {
    id: "poly",
    name: "Polyphony",
    sub: "independent lines interweaving",
    on: ["melody", "counter", "bass"],
    desc: "Two or more equal melodies at once. Listen to how the lines answer each other — this is fugue territory.",
  },
  {
    id: "full",
    name: "Full arrangement",
    sub: "every layer in place",
    on: ["texture", "melody", "counter", "harmony", "bass", "drums"],
    desc: "All six layers stacked. Each occupies its own frequency range and rhythmic space, so nothing fights.",
  },
];

/* ------------------------------------------------------------------ */

export default function LayersOfMusic() {
  const [audioReady, setAudioReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [globalStep, setGlobalStep] = useState(-1);
  const [muted, setMuted] = useState({});
  const [solo, setSolo] = useState({});
  const [expanded, setExpanded] = useState(null);
  const [activePreset, setActivePreset] = useState("full");

  const stepRef = useRef(0);
  const nodes = useRef(null);
  const loopId = useRef(null);

  const bar = globalStep >= 0 ? Math.floor(globalStep / 16) % 4 : 0;
  const step = globalStep >= 0 ? globalStep % 16 : -1;

  /* ---- audio graph, built once on first play ---- */
  const buildAudio = useCallback(async () => {
    await Tone.start();
    if (nodes.current) return;

    const master = new Tone.Gain(0.85).toDestination();
    const verb = new Tone.Freeverb({ roomSize: 0.72, dampening: 2400, wet: 0.22 }).connect(master);

    const ch = {};
    LAYERS.forEach((l) => {
      ch[l.id] = new Tone.Channel({ volume: 0 }).connect(master);
      ch[l.id].connect(verb);
    });
    ch.drums.volume.value = -2;
    ch.texture.volume.value = -10;
    ch.harmony.volume.value = -6;
    ch.counter.volume.value = -7;
    ch.melody.volume.value = -4;
    ch.bass.volume.value = -3;

    const kick = new Tone.MembraneSynth({
      pitchDecay: 0.04, octaves: 6,
      envelope: { attack: 0.001, decay: 0.32, sustain: 0 },
    }).connect(ch.drums);

    const snare = new Tone.NoiseSynth({
      noise: { type: "pink" },
      envelope: { attack: 0.001, decay: 0.16, sustain: 0 },
    }).connect(ch.drums);

    const hatFilter = new Tone.Filter(8000, "highpass").connect(ch.drums);
    const hat = new Tone.NoiseSynth({
      noise: { type: "white" },
      envelope: { attack: 0.001, decay: 0.045, sustain: 0 },
      volume: -8,
    }).connect(hatFilter);

    const bass = new Tone.MonoSynth({
      oscillator: { type: "sawtooth" },
      filter: { Q: 1, type: "lowpass", rolloff: -24 },
      envelope: { attack: 0.005, decay: 0.25, sustain: 0.35, release: 0.15 },
      filterEnvelope: { attack: 0.004, decay: 0.18, sustain: 0.28, baseFrequency: 90, octaves: 2.4 },
    }).connect(ch.bass);

    const harmony = new Tone.PolySynth(Tone.Synth, {
      oscillator: { type: "triangle" },
      envelope: { attack: 0.01, decay: 0.3, sustain: 0.12, release: 0.4 },
    }).connect(ch.harmony);

    const counter = new Tone.AMSynth({
      harmonicity: 2,
      envelope: { attack: 0.03, decay: 0.3, sustain: 0.3, release: 0.5 },
    }).connect(ch.counter);

    const melody = new Tone.Synth({
      oscillator: { type: "triangle8" },
      envelope: { attack: 0.015, decay: 0.2, sustain: 0.35, release: 0.3 },
    }).connect(ch.melody);

    const padFilter = new Tone.Filter(1400, "lowpass").connect(ch.texture);
    const pad = new Tone.PolySynth(Tone.Synth, {
      oscillator: { type: "sawtooth" },
      envelope: { attack: 0.9, decay: 0.5, sustain: 0.8, release: 1.6 },
    }).connect(padFilter);

    nodes.current = { master, verb, ch, kick, snare, hat, bass, harmony, counter, melody, pad };

    Tone.Transport.bpm.value = 96;
    loopId.current = Tone.Transport.scheduleRepeat((time) => {
      const g = stepRef.current;
      const s = g % 16;
      const b = Math.floor(g / 16) % 4;
      const chord = CHORDS[b];
      const n = nodes.current;

      if (s % 2 === 0) n.hat.triggerAttackRelease("16n", time);
      if (OPEN_HAT.includes(s)) n.hat.triggerAttackRelease("8n", time, 0.7);
      if (KICK.includes(s)) n.kick.triggerAttackRelease("A1", "8n", time);
      if (SNARE.includes(s)) n.snare.triggerAttackRelease("8n", time);

      const bi = BASS_STEPS.indexOf(s);
      if (bi >= 0) n.bass.triggerAttackRelease(chord.bass[BASS_NOTE_IDX[bi]], "16n", time);

      if (STAB_STEPS.includes(s)) n.harmony.triggerAttackRelease(chord.stab, "8n", time, 0.7);
      if (s === 0) n.pad.triggerAttackRelease(chord.pad, "1m", time, 0.5);

      const mNote = MELODY[b][s];
      if (mNote) n.melody.triggerAttackRelease(mNote, "8n", time, 0.85);
      const cNote = COUNTER[b][s];
      if (cNote) n.counter.triggerAttackRelease(cNote, "4n", time, 0.7);

      Tone.Draw.schedule(() => setGlobalStep(g), time);
      stepRef.current = (g + 1) % 64;
    }, "16n");

    setAudioReady(true);
  }, []);

  /* ---- apply mute/solo to channels ---- */
  useEffect(() => {
    if (!nodes.current) return;
    const anySolo = Object.values(solo).some(Boolean);
    LAYERS.forEach((l) => {
      nodes.current.ch[l.id].mute = anySolo ? !solo[l.id] : !!muted[l.id];
    });
  }, [muted, solo, audioReady]);

  useEffect(() => {
    return () => {
      Tone.Transport.stop();
      Tone.Transport.cancel();
    };
  }, []);

  const togglePlay = async () => {
    await buildAudio();
    if (Tone.Transport.state === "started") {
      Tone.Transport.stop();
      setPlaying(false);
      setGlobalStep(-1);
      stepRef.current = 0;
    } else {
      stepRef.current = 0;
      Tone.Transport.start("+0.05");
      setPlaying(true);
    }
  };

  const isSilenced = (id) => {
    const anySolo = Object.values(solo).some(Boolean);
    return anySolo ? !solo[id] : !!muted[id];
  };

  const toggleMute = (id) => {
    setActivePreset(null);
    setMuted((m) => ({ ...m, [id]: !m[id] }));
  };

  const toggleSolo = (id) => {
    setActivePreset(null);
    setSolo((s) => ({ ...s, [id]: !s[id] }));
  };

  const applyPreset = (p) => {
    setActivePreset(p.id);
    setSolo({});
    const m = {};
    LAYERS.forEach((l) => (m[l.id] = !p.on.includes(l.id)));
    setMuted(m);
    if (!playing) togglePlay();
  };

  const activeCount = LAYERS.filter((l) => !isSilenced(l.id)).length;

  return (
    <div className="lom-root">
      <style>{css}</style>

      {/* ---------- header ---------- */}
      <header className="hdr">
        <div className="eyebrow">Interactive listening guide</div>
        <h1>
          A piece of music,
          <br />
          <em>taken apart.</em>
        </h1>
        <p className="lede">
          Almost everything you hear — a pop song, a film score, a club track — is built from the
          same six layers, stacked from low frequencies to high. Press play, then mute and solo
          layers to hear what each one actually does.
        </p>
      </header>

      {/* ---------- transport ---------- */}
      <div className="transport">
        <button className={`play ${playing ? "on" : ""}`} onClick={togglePlay}>
          {playing ? "■ Stop" : "▶ Play the loop"}
        </button>
        <div className="readout">
          <span className="ro-label">Chord</span>
          <span className="ro-value">{playing ? CHORDS[bar].name : "—"}</span>
        </div>
        <div className="readout">
          <span className="ro-label">Bar</span>
          <span className="ro-value">{playing ? `${bar + 1} / 4` : "—"}</span>
        </div>
        <div className="readout">
          <span className="ro-label">Layers live</span>
          <span className="ro-value">{activeCount} / 6</span>
        </div>
        <div className="readout tempo">
          <span className="ro-label">Tempo</span>
          <span className="ro-value">96 BPM</span>
        </div>
      </div>

      {/* ---------- stem stack ---------- */}
      <div className="stack-wrap">
        <div className="freq-axis" aria-hidden="true">
          <span>HIGH</span>
          <span className="axis-line" />
          <span>LOW</span>
        </div>

        <div className="stack">
          {LAYERS.map((layer) => {
            const silenced = isSilenced(layer.id);
            const hits = layerHits(layer.id, bar);
            const open = expanded === layer.id;
            return (
              <div key={layer.id} className={`row ${silenced ? "silenced" : ""} ${open ? "open" : ""}`}>
                <div className="row-main">
                  <button
                    className="row-id"
                    onClick={() => setExpanded(open ? null : layer.id)}
                    aria-expanded={open}
                    style={{ "--lc": layer.color }}
                  >
                    <span className="swatch" />
                    <span className="names">
                      <span className="lname">{layer.name}</span>
                      <span className="ltag">{layer.tag}</span>
                    </span>
                    <span className="chev">{open ? "−" : "+"}</span>
                  </button>

                  <div className="cells" style={{ "--lc": layer.color }}>
                    {layer.id === "texture" ? (
                      <div className={`pad-bar ${playing && !silenced ? "breathing" : ""}`}>
                        <span>{CHORDS[bar].name} — held all bar</span>
                        {playing && step >= 0 && (
                          <span className="pad-head" style={{ left: `${(step / 16) * 100}%` }} />
                        )}
                      </div>
                    ) : (
                      Array.from({ length: 16 }, (_, i) => {
                        const hit = hits.has(i);
                        const now = i === step && playing;
                        return (
                          <span
                            key={i}
                            className={[
                              "cell",
                              hit ? "hit" : "",
                              now ? "now" : "",
                              i % 4 === 0 ? "beat" : "",
                            ].join(" ")}
                          >
                            {layer.id === "drums" && hit && (
                              <span className="drum-marks">
                                {KICK.includes(i) && <i className="k" />}
                                {SNARE.includes(i) && <i className="s" />}
                                <i className="h" />
                              </span>
                            )}
                          </span>
                        );
                      })
                    )}
                  </div>

                  <div className="row-ctrl">
                    <button
                      className={`ctrl mute ${muted[layer.id] ? "active" : ""}`}
                      onClick={() => toggleMute(layer.id)}
                      title={muted[layer.id] ? "Unmute" : "Mute"}
                    >
                      M
                    </button>
                    <button
                      className={`ctrl solo ${solo[layer.id] ? "active" : ""}`}
                      onClick={() => toggleSolo(layer.id)}
                      title={solo[layer.id] ? "Unsolo" : "Solo — hear this layer alone"}
                    >
                      S
                    </button>
                  </div>
                </div>

                {open && (
                  <div className="row-detail" style={{ "--lc": layer.color }}>
                    <div className="detail-col">
                      <h4>What it does</h4>
                      <p>{layer.role}</p>
                      <h4>Listen for</h4>
                      <p>{layer.listen}</p>
                    </div>
                    <div className="detail-col">
                      <h4>Take it away…</h4>
                      <p>{layer.without}</p>
                      <h4>In the real world</h4>
                      <p>{layer.examples}</p>
                      <div className="freq-chip">{layer.freq}</div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <p className="hint">
        <b>M</b> mutes a layer · <b>S</b> solos it (silences everything else) · tap a layer's name
        to read what it's doing.
      </p>

      {/* ---------- texture lesson ---------- */}
      <section className="textures">
        <div className="eyebrow">One loop, four textures</div>
        <h2>How the layers combine is called texture</h2>
        <p className="sec-lede">
          Musicians name arrangements by how many independent parts sound at once. These presets
          reconfigure the same loop — listen to how differently it behaves.
        </p>
        <div className="preset-grid">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              className={`preset ${activePreset === p.id ? "active" : ""}`}
              onClick={() => applyPreset(p)}
            >
              <span className="p-name">{p.name}</span>
              <span className="p-sub">{p.sub}</span>
              <span className="p-dots">
                {LAYERS.slice().reverse().map((l) => (
                  <i
                    key={l.id}
                    style={{
                      background: p.on.includes(l.id) ? l.color : "transparent",
                      borderColor: l.color,
                    }}
                  />
                ))}
              </span>
              <span className="p-desc">{p.desc}</span>
            </button>
          ))}
        </div>
      </section>

      {/* ---------- closing note ---------- */}
      <footer className="foot">
        <h3>The takeaway</h3>
        <p>
          A good arrangement is a frequency and rhythm agreement: drums own the pulse, bass owns the
          low end, harmony fills the middle, melody takes the spotlight, counter-lines answer in the
          gaps, and texture glues it together. Next time a song comes on, try muting layers in your
          head — pick one part and follow only it. That's how producers and arrangers listen.
        </p>
      </footer>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Styles                                                            */
/* ------------------------------------------------------------------ */

const css = `
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@400;600&family=Newsreader:ital,opsz,wght@1,6..72,400&display=swap');

.lom-root {
  --bg: #0F1218;
  --panel: #161B24;
  --panel-2: #1C2230;
  --line: #2A3242;
  --ink: #E8E6DF;
  --dim: #9AA3B2;
  min-height: 100vh;
  background:
    radial-gradient(1100px 500px at 75% -10%, rgba(143,166,217,0.10), transparent 60%),
    radial-gradient(900px 500px at 10% 110%, rgba(201,86,63,0.08), transparent 60%),
    var(--bg);
  color: var(--ink);
  font-family: 'Space Grotesk', system-ui, sans-serif;
  padding: clamp(20px, 4vw, 56px) clamp(16px, 5vw, 72px) 64px;
}
.lom-root *, .lom-root *::before, .lom-root *::after { box-sizing: border-box; }
.lom-root button { font-family: inherit; cursor: pointer; }
.lom-root button:focus-visible { outline: 2px solid #8FA6D9; outline-offset: 2px; }

.eyebrow {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; letter-spacing: 0.22em; text-transform: uppercase;
  color: var(--dim); margin-bottom: 14px;
}
.hdr { max-width: 860px; margin-bottom: 34px; }
.hdr h1 {
  font-size: clamp(34px, 5.5vw, 62px);
  line-height: 1.02; margin: 0 0 18px; font-weight: 700; letter-spacing: -0.02em;
}
.hdr h1 em {
  font-family: 'Newsreader', serif; font-style: italic; font-weight: 400;
  color: #8FA6D9;
}
.lede { color: var(--dim); font-size: clamp(15px, 1.6vw, 17px); line-height: 1.65; max-width: 640px; margin: 0; }

/* transport */
.transport {
  display: flex; flex-wrap: wrap; align-items: stretch; gap: 10px;
  margin-bottom: 26px;
}
.play {
  background: var(--ink); color: var(--bg); border: none; border-radius: 8px;
  padding: 12px 26px; font-size: 15px; font-weight: 700; letter-spacing: 0.02em;
  transition: transform 0.12s ease, background 0.2s;
}
.play:hover { transform: translateY(-1px); }
.play.on { background: #C9563F; color: var(--ink); }
.readout {
  background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  padding: 8px 16px; display: flex; flex-direction: column; justify-content: center; min-width: 92px;
}
.ro-label {
  font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 0.18em;
  text-transform: uppercase; color: var(--dim);
}
.ro-value { font-family: 'JetBrains Mono', monospace; font-size: 15px; font-weight: 600; }

/* stack + frequency axis */
.stack-wrap { display: flex; gap: 12px; }
.freq-axis {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 0.2em;
  color: var(--dim); padding-top: 6px;
  writing-mode: initial;
}
.axis-line { flex: 1; width: 1px; background: linear-gradient(#8FA6D9, #C9563F); opacity: 0.5; }

.stack { flex: 1; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.row {
  background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  transition: opacity 0.25s ease, border-color 0.25s;
}
.row.silenced { opacity: 0.38; }
.row.open { border-color: #3A465C; background: var(--panel-2); }
.row-main {
  display: grid; grid-template-columns: 190px 1fr 76px;
  align-items: center; gap: 12px; padding: 8px 10px;
}
.row-id {
  display: flex; align-items: center; gap: 10px; background: none; border: none;
  color: var(--ink); text-align: left; padding: 6px 4px; border-radius: 6px;
}
.row-id:hover { background: rgba(255,255,255,0.04); }
.swatch { width: 10px; height: 34px; border-radius: 3px; background: var(--lc); flex-shrink: 0; }
.names { display: flex; flex-direction: column; min-width: 0; }
.lname { font-weight: 700; font-size: 14px; letter-spacing: 0.01em; white-space: nowrap; }
.ltag {
  font-family: 'Newsreader', serif; font-style: italic; font-size: 13px; color: var(--dim);
}
.chev { margin-left: auto; color: var(--dim); font-size: 16px; font-weight: 400; }

.cells { display: grid; grid-template-columns: repeat(16, 1fr); gap: 3px; height: 40px; }
.cell {
  position: relative; border-radius: 3px; background: rgba(255,255,255,0.035);
  display: flex; align-items: flex-end; justify-content: center;
}
.cell.beat { background: rgba(255,255,255,0.07); }
.cell.hit { background: color-mix(in srgb, var(--lc) 34%, transparent); }
.cell.hit::after {
  content: ""; position: absolute; inset: auto 20% 20% 20%; height: 45%;
  background: var(--lc); border-radius: 2px;
}
.cell.now { box-shadow: inset 0 0 0 2px var(--ink); }
.cell.now.hit::after { filter: brightness(1.4); }
.drum-marks { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; z-index: 1; }
.drum-marks i { display: block; border-radius: 2px; background: var(--ink); }
.drum-marks .k { width: 60%; height: 8px; background: #C9563F; }
.drum-marks .s { width: 45%; height: 6px; background: #E8B44C; }
.drum-marks .h { width: 25%; height: 3px; background: rgba(232,230,223,0.8); }
.cell.hit .drum-marks ~ *, .cell.hit:has(.drum-marks)::after { display: none; }

.pad-bar {
  grid-column: 1 / -1; position: relative; border-radius: 4px;
  background: linear-gradient(90deg, color-mix(in srgb, var(--lc) 28%, transparent), color-mix(in srgb, var(--lc) 12%, transparent));
  display: flex; align-items: center; padding: 0 12px; overflow: hidden;
  font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--ink); letter-spacing: 0.06em;
}
.pad-bar.breathing { animation: breathe 2.5s ease-in-out infinite; }
@keyframes breathe { 0%,100% { filter: brightness(1); } 50% { filter: brightness(1.25); } }
.pad-head { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--ink); opacity: 0.8; }

.row-ctrl { display: flex; gap: 6px; justify-content: flex-end; }
.ctrl {
  width: 32px; height: 32px; border-radius: 6px; border: 1px solid var(--line);
  background: transparent; color: var(--dim);
  font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 600;
  transition: all 0.15s;
}
.ctrl:hover { border-color: var(--dim); color: var(--ink); }
.ctrl.mute.active { background: #C9563F; border-color: #C9563F; color: var(--ink); }
.ctrl.solo.active { background: #E4C662; border-color: #E4C662; color: #10141C; }

.row-detail {
  display: grid; grid-template-columns: 1fr 1fr; gap: 8px 28px;
  padding: 14px 18px 18px; border-top: 1px solid var(--line);
}
.row-detail h4 {
  font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.18em;
  text-transform: uppercase; color: var(--lc); margin: 10px 0 4px;
}
.row-detail h4:first-child { margin-top: 0; }
.row-detail p { margin: 0; font-size: 13.5px; line-height: 1.6; color: #C6CBD6; }
.freq-chip {
  display: inline-block; margin-top: 12px; padding: 4px 10px; border-radius: 999px;
  border: 1px solid var(--lc); color: var(--lc);
  font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.08em;
}

.hint { color: var(--dim); font-size: 13px; margin: 16px 0 0 0; }
.hint b { font-family: 'JetBrains Mono', monospace; color: var(--ink); }

/* textures section */
.textures { margin-top: 64px; max-width: 1000px; }
.textures h2 { font-size: clamp(24px, 3.4vw, 36px); margin: 0 0 12px; letter-spacing: -0.01em; }
.sec-lede { color: var(--dim); max-width: 620px; line-height: 1.6; margin: 0 0 24px; }
.preset-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.preset {
  text-align: left; background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
  padding: 18px; color: var(--ink); display: flex; flex-direction: column; gap: 6px;
  transition: border-color 0.2s, transform 0.15s;
}
.preset:hover { transform: translateY(-2px); border-color: #3A465C; }
.preset.active { border-color: #8FA6D9; background: var(--panel-2); }
.p-name { font-weight: 700; font-size: 17px; }
.p-sub { font-family: 'Newsreader', serif; font-style: italic; color: var(--dim); font-size: 14px; }
.p-dots { display: flex; gap: 5px; margin: 6px 0 4px; }
.p-dots i { width: 12px; height: 12px; border-radius: 3px; border: 1px solid; display: block; }
.p-desc { font-size: 12.5px; line-height: 1.55; color: #B9BFCB; }

.foot { margin-top: 60px; max-width: 660px; border-top: 1px solid var(--line); padding-top: 28px; }
.foot h3 { margin: 0 0 10px; font-size: 18px; }
.foot p { color: var(--dim); line-height: 1.7; margin: 0; font-size: 14.5px; }

@media (max-width: 760px) {
  .stack-wrap { flex-direction: column; }
  .freq-axis { flex-direction: row; width: 100%; padding: 0; }
  .axis-line { height: 1px; width: auto; background: linear-gradient(90deg, #8FA6D9, #C9563F); }
  .row-main { grid-template-columns: 1fr; gap: 8px; }
  .cells { height: 30px; }
  .row-ctrl { justify-content: flex-start; }
  .row-detail { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  .pad-bar.breathing { animation: none; }
  .play:hover, .preset:hover { transform: none; }
}
`;
