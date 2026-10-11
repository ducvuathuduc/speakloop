import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { C, MaskWords, Scene, fade, inOut, ramp } from "./lib";
import { UICard, UIState } from "./UICard";
import ENV from "./vo_env.json";

// 8. REAL — the shipped card components (feat/ui), driven at real speed: say it, see every sound,
// play it back, drill the fix. Coordinates are in the card's 768x480 base canvas
// (measured with the Measure composition).
export const Z = 1.75; // card zoom: 768x480 -> 1344x840
const CX = 960,
  CY = 552; // screen point the camera centres on

// learner line plays at 90 (recording) and 378 (karaoke playback); "Walked." at 502 (drill).
// Keep in sync with src/vo.json (scene starts at 68 s).
export const REAL_VO = { listen: 90, karaoke: 378, drill: 502 };

const lvl = (f: number, at: number, env: number[]) => {
  const i = f - at;
  return i >= 0 && i < env.length ? env[i] : 0;
};

type Shot = { at: number; fx: number; fy: number; k: number; len: number };
// camera keyframes: eased from the previous shot over `len` frames ending at `at`
const SHOTS: Shot[] = [
  { at: 0, fx: 384, fy: 240, k: 1, len: 1 },
  { at: 176, fx: 300, fy: 300, k: 1.12, len: 56 },
  { at: 206, fx: 384, fy: 240, k: 1, len: 14 },
  { at: 252, fx: 567, fy: 230, k: 1.42, len: 40 },
  { at: 330, fx: 384, fy: 240, k: 1, len: 28 },
  { at: 392, fx: 384, fy: 300, k: 1.2, len: 30 },
  { at: 476, fx: 384, fy: 240, k: 1, len: 16 },
  { at: 520, fx: 430, fy: 330, k: 1.22, len: 36 },
];
const camera = (f: number) => {
  let cur = SHOTS[0];
  for (let i = 1; i < SHOTS.length; i++) {
    const s = SHOTS[i];
    const p = ramp(f, s.at - s.len, s.at, 0, 1, inOut);
    if (p <= 0) break;
    cur = {
      at: s.at,
      len: s.len,
      fx: interpolate(p, [0, 1], [cur.fx, s.fx]),
      fy: interpolate(p, [0, 1], [cur.fy, s.fy]),
      k: interpolate(p, [0, 1], [cur.k, s.k]),
    };
  }
  return cur;
};

// cursor path: [frame, x, y] in base coords
const PATH: [number, number, number][] = [
  [40, 470, 470],
  [78, 64, 418],
  [150, 64, 418],
  [158, 64, 418],
  [290, 300, 380],
  [334, 668, 40],
  [346, 668, 40],
  [372, 112, 428],
  [400, 112, 428],
  [440, 230, 470],
  [470, 420, 470],
  [492, 591, 424],
  [548, 591, 424],
  [580, 640, 470],
];
const CLICKS = [80, 156, 338, 374, 494, 546];
const cursorAt = (f: number) => {
  if (f <= PATH[0][0]) return { x: PATH[0][1], y: PATH[0][2] };
  for (let i = 1; i < PATH.length; i++) {
    const [f1, x1, y1] = PATH[i];
    const [f0, x0, y0] = PATH[i - 1];
    if (f <= f1) {
      const p = ramp(f, f0, f1, 0, 1, inOut);
      return { x: interpolate(p, [0, 1], [x0, x1]), y: interpolate(p, [0, 1], [y0, y1]) };
    }
  }
  const l = PATH[PATH.length - 1];
  return { x: l[1], y: l[2] };
};

const stateAt = (f: number): UIState => {
  if (f < 196) {
    if (f >= 84 && f < 158) return { kind: "listen", rec: { state: "recording", level: 0.15 + 0.85 * lvl(f, REAL_VO.listen, ENV.learner) } };
    if (f >= 158) return { kind: "listen", rec: { state: "busy" } };
    return { kind: "listen" };
  }
  if (f < 346) return { kind: "split" };
  if (f < 466) {
    const K = REAL_VO.karaoke;
    const playing = f >= K && f < K + 56;
    const t = f < K || f >= K + 62 ? null : clipToFixture((f - K) / 30);
    return { kind: "karaoke", t, playing };
  }
  if (f >= 496 && f < 548) return { kind: "drill", rec: { state: "recording", level: 0.15 + 0.85 * lvl(f, REAL_VO.drill, ENV.walked) } };
  if (f >= 548 && f < 566) return { kind: "drill", rec: { state: "busy" } };
  if (f >= 566) return { kind: "drill", step: 4, secondsLeft: 78, last: { word: "walk / walked", ok: true, note: "Clear /t/" } };
  return { kind: "drill" };
};
const SWAPS = [196, 346, 466];

// Karaoke playhead follows the actual learner clip: word onsets in public/vo/learner.wav (faster-whisper word
// timestamps refined with the clip's energy envelope) mapped onto the fixture's word times.
const CLIP_T = [0, 0.05, 0.16, 0.43, 0.58, 0.68, 0.95, 1.58];
const FIX_T = [0.32, 0.32, 0.66, 1.14, 1.34, 1.52, 1.96, 2.62];
const clipToFixture = (c: number) =>
  c >= CLIP_T[CLIP_T.length - 1] ? FIX_T[FIX_T.length - 1] + (c - CLIP_T[CLIP_T.length - 1]) : interpolate(c, CLIP_T, FIX_T);

const CAPS: [number, number, string, string][] = [
  [44, 190, "1", "Say it once."],
  [204, 340, "2", "Every sound checked, not just the words."],
  [354, 460, "3", "Play it back, one sound at a time."],
  [474, 600, "4", "Then drill the one fix."],
];

const Cursor: React.FC<{ x: number; y: number; press: number; o: number }> = ({ x, y, press, o }) => (
  <div style={{ position: "absolute", left: x, top: y, opacity: o, pointerEvents: "none" }}>
    <div
      style={{
        position: "absolute",
        left: -40,
        top: -40,
        width: 80,
        height: 80,
        borderRadius: 40,
        border: `4px solid ${C.text}`,
        opacity: press > 0 ? (1 - press) * 0.8 : 0,
        transform: `scale(${0.4 + press * 1.1})`,
      }}
    />
    <svg
      width="46"
      height="54"
      viewBox="0 0 23 27"
      style={{
        position: "absolute",
        left: -4,
        top: -3,
        transform: `scale(${1 - 0.14 * Math.sin(Math.PI * Math.min(1, press * 2))})`,
        transformOrigin: "4px 3px",
        filter: "drop-shadow(0 6px 10px rgba(0,0,0,0.55))",
      }}
    >
      <path d="M2 1.5 L2 22 L7.4 17.2 L11 25.2 L14.6 23.6 L11.1 15.8 L18.4 15.6 Z" fill={C.text} stroke="#0B0D11" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  </div>
);

export const Real: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const cam = camera(f);
  const ox = CX - cam.fx * Z * cam.k;
  const oy = CY - cam.fy * Z * cam.k;
  const enter = ramp(f, 6, 42);
  const swap = SWAPS.find((s) => f >= s && f < s + 8);
  const cur = stateAt(f);
  const prev = swap !== undefined ? stateAt(swap - 1) : null;
  const k = swap !== undefined ? ramp(f, swap, swap + 8) : 1;
  const c = cursorAt(f);
  const click = CLICKS.find((cf) => f >= cf && f < cf + 16);
  const press = click !== undefined ? (f - click) / 16 : 0;
  const cursorO = fade(f, 40, 8) * (1 - ramp(f, 580, 592));
  return (
    <Scene dur={dur}>
      <div style={{ position: "absolute", top: 34, left: 0, right: 0, textAlign: "center", fontSize: 54, fontWeight: 700, letterSpacing: "-0.02em", opacity: 1 - ramp(f, 100, 116) }}>
        <MaskWords text="The real card. Real speed." at={2} base={2} colors={{ 1: C.accent }} />
      </div>
      <div
        style={{
          position: "absolute",
          left: ox,
          top: oy + (1 - enter) * 90,
          width: 768 * Z,
          height: 480 * Z,
          transform: `scale(${cam.k * interpolate(enter, [0, 1], [0.95, 1])})`,
          transformOrigin: "0 0",
          opacity: fade(f, 6, 8),
          borderRadius: 16 * Z,
          boxShadow: "0 50px 120px rgba(0,0,0,0.6), 0 0 0 1.5px rgba(255,255,255,0.07)",
        }}
      >
        {prev && <UICard s={prev} zoom={Z} style={{ position: "absolute", inset: 0, opacity: 1 - k }} />}
        <UICard s={cur} zoom={Z} style={{ position: "absolute", inset: 0, opacity: prev ? k : 1, transform: prev ? `translateY(${(1 - k) * 18}px)` : undefined }} />
      </div>
      {f >= 566 && (
        <div
          style={{
            position: "absolute",
            left: ox + (24 - 12) * Z * cam.k,
            top: oy + (413 - 10) * Z * cam.k,
            width: (242 + 24) * Z * cam.k,
            height: (22 + 20) * Z * cam.k,
            borderRadius: 999,
            border: `3px solid ${C.ok}`,
            boxShadow: `0 0 ${40 * ramp(f, 566, 590)}px rgba(86,180,233,0.45)`,
            opacity: fade(f, 566, 6) * (1 - ramp(f, dur - 12, dur)),
            transform: `scale(${ramp(f, 566, 584, 1.12, 1)})`,
          }}
        />
      )}
      <Cursor x={ox + c.x * Z * cam.k} y={oy + c.y * Z * cam.k} press={press} o={cursorO} />
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 210, background: "linear-gradient(rgba(11,13,17,0), rgba(11,13,17,0.94) 55%)" }} />
      {CAPS.map(([a, b, n, txt]) => {
        const o = fade(f, a, 8) * (1 - ramp(f, b - 10, b));
        if (o <= 0) return null;
        return (
          <div key={n} style={{ position: "absolute", bottom: 46, left: 0, right: 0, display: "flex", justifyContent: "center", alignItems: "center", gap: 22, opacity: o, transform: `translateY(${ramp(f, a, a + 18, 20, 0)}px)` }}>
            <span style={{ width: 54, height: 54, borderRadius: 27, background: C.accent, color: C.onAccent, fontSize: 30, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center" }}>{n}</span>
            <span style={{ fontSize: 46, fontWeight: 700, letterSpacing: "-0.015em" }}>{txt}</span>
          </div>
        );
      })}
      <div
        style={{
          position: "absolute",
          top: 22,
          right: 36,
          fontSize: 24,
          color: C.text2,
          opacity: fade(f, 160, 10) * (1 - ramp(f, dur - 30, dur - 20)) * Math.max(0, Math.min(1, (1.12 - cam.k) / 0.1)),
        }}
      >
        SpeakLoop card · its own UI components · demo data · real speed
      </div>
    </Scene>
  );
};
