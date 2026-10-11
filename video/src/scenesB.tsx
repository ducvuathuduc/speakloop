import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C, Chip, Frame3D, Logo, Mask, MaskWords, PHON, Scene, fade, inOut, ramp, stagger } from "./lib";
import { Lockup } from "./scenesA";

const center: React.CSSProperties = { alignItems: "center", justifyContent: "center", textAlign: "center" };
const title: React.CSSProperties = { position: "absolute", top: 110, left: 0, right: 0, textAlign: "center", fontSize: 64, fontWeight: 700, letterSpacing: "-0.025em" };

// ---------------------------------------------------------------------------------------------
// 7. MEMORY — weak-sound rings (demo data) + FSRS line.
export const Memory: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const rings = [
    { v: 42, name: "-ed endings", ph: "/t/ after /k p s/", today: true },
    { v: 61, name: "Final -s", ph: "/s z/ word-final" },
    { v: 74, name: "Voiced th", ph: "/ð/ in the, this" },
  ];
  const R = 140,
    SW = 26,
    CIRC = 2 * Math.PI * R;
  return (
    <Scene dur={dur}>
      <div style={title}>
        <MaskWords text="It remembers the sounds you miss." at={2} base={2} />
      </div>
      <div style={{ position: "absolute", top: 60, right: 80, opacity: fade(f, 20, 8) }}>
        <Chip style={{ fontSize: 22 }}>Demo data</Chip>
      </div>
      <div style={{ position: "absolute", top: 300, left: 0, right: 0, display: "flex", justifyContent: "center", gap: 120 }}>
        {rings.map((r, i) => {
          const a = 24 + stagger(i, 10);
          const p = ramp(f, a, a + 60);
          const val = Math.round(r.v * p);
          return (
            <div key={i} style={{ width: 380, display: "flex", flexDirection: "column", alignItems: "center", opacity: fade(f, a - 6, 6), transform: `translateY(${ramp(f, a - 6, a + 20, 40, 0)}px)` }}>
              <div style={{ position: "relative", width: 2 * R + SW, height: 2 * R + SW }}>
                <svg width={2 * R + SW} height={2 * R + SW} style={{ transform: "rotate(-90deg)" }}>
                  <circle cx={R + SW / 2} cy={R + SW / 2} r={R} stroke={C.track} strokeWidth={SW} fill="none" />
                  <circle
                    cx={R + SW / 2}
                    cy={R + SW / 2}
                    r={R}
                    stroke={r.today ? C.accent : C.text2}
                    strokeWidth={SW}
                    fill="none"
                    strokeLinecap="round"
                    strokeDasharray={`${CIRC * (r.v / 100) * p} ${CIRC}`}
                  />
                </svg>
                <AbsoluteFill style={center}>
                  <span style={{ fontSize: 84, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                    {val}
                    <span style={{ fontSize: 40, color: C.text2 }}>%</span>
                  </span>
                </AbsoluteFill>
              </div>
              <div style={{ marginTop: 34, fontSize: 40, fontWeight: 700, display: "flex", alignItems: "center", gap: 14 }}>
                {r.name}
                {r.today && (
                  <span style={{ background: C.accent, color: C.onAccent, fontSize: 22, padding: "5px 14px", borderRadius: 999, fontWeight: 700 }}>Today</span>
                )}
              </div>
              <div style={{ fontFamily: PHON, fontSize: 32, color: C.text2, marginTop: 10 }}>{r.ph}</div>
            </div>
          );
        })}
      </div>
      <div style={{ position: "absolute", bottom: 110, left: 0, right: 0, textAlign: "center", fontSize: 42, color: C.text2, fontWeight: 500 }}>
        <MaskWords text="FSRS spaced repetition brings each one back before you forget it." at={150} base={2} colors={{ 0: C.text }} />
      </div>
    </Scene>
  );
};

// ---------------------------------------------------------------------------------------------
// 9. PROOF — benchmark bars, exact figures from benchmarks/RESULTS.md.
const Bar: React.FC<{ at: number; v: number; label: string; win?: boolean; W: number }> = ({ at, v, label, win, W }) => {
  const f = useCurrentFrame();
  const p = ramp(f, at, at + 44);
  return (
    <div style={{ display: "flex", alignItems: "center", height: 84, gap: 26 }}>
      <div style={{ width: 330, fontSize: 28, color: win ? C.text : C.text2, fontWeight: win ? 700 : 500, textAlign: "right", opacity: fade(f, at - 4, 6) }}>{label}</div>
      <div style={{ position: "relative", width: W, height: 60 }}>
        <div style={{ position: "absolute", inset: 0, borderRadius: 10, background: "rgba(255,255,255,0.03)" }} />
        <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: W * v * p, borderRadius: 10, background: win ? C.accent : "#4A5363" }} />
        <div
          style={{
            position: "absolute",
            left: W * v * p + 22,
            top: -6,
            fontSize: 60,
            fontWeight: 700,
            color: win ? C.text : C.text2,
            fontVariantNumeric: "tabular-nums",
            opacity: ramp(f, at + 26, at + 36, 0, 1),
          }}
        >
          {v.toFixed(2)}
        </div>
      </div>
    </div>
  );
};

export const Proof: React.FC<{ dur: number; vertical?: boolean }> = ({ dur, vertical }) => {
  const f = useCurrentFrame();
  const W = vertical ? 480 : 920;
  const H = vertical ? -36 : 0; // teaser: land the 2.4x earlier so the precision line holds before the cut
  return (
    <Scene dur={dur}>
      <AbsoluteFill style={center}>
        <div style={{ fontSize: vertical ? 96 : 104, fontWeight: 700, letterSpacing: "-0.03em", padding: vertical ? "0 80px" : 0 }}>
          <MaskWords text="Does it really hear more?" at={2} out={62} />
        </div>
      </AbsoluteFill>
      <div
        style={
          vertical
            ? { position: "absolute", top: 260, left: 40, display: "flex", flexDirection: "column", gap: 60 }
            : { position: "absolute", top: 250, left: 60, display: "flex", flexDirection: "column", gap: 90 }
        }
      >
        <div style={{ opacity: fade(f, 74, 8) }}>
          <div style={{ fontSize: 38, fontWeight: 700, marginLeft: vertical ? 30 : 356, marginBottom: 14 }}>Recall · real errors caught</div>
          <Bar at={84} v={0.533} label="SpeakLoop" win W={W} />
          <Bar at={96} v={0.219} label="Transcript diff" W={W} />
        </div>
        <div style={{ opacity: fade(f, 140, 8) }}>
          <div style={{ fontSize: 38, fontWeight: 700, marginLeft: vertical ? 30 : 356, marginBottom: 14 }}>F1</div>
          <Bar at={150} v={0.56} label="SpeakLoop" win W={W} />
          <Bar at={162} v={0.323} label="Transcript diff" W={W} />
        </div>
      </div>
      <div
        style={
          vertical
            ? { position: "absolute", top: 1180, left: 0, right: 0, textAlign: "center" }
            : { position: "absolute", top: 340, right: 40, width: 500, textAlign: "left" }
        }
      >
        <div style={{ fontSize: vertical ? 220 : 210, fontWeight: 800, letterSpacing: "-0.05em", color: C.accent, lineHeight: 1 }}>
          <Mask at={232 + H} dur={26}>
            2.4×
          </Mask>
        </div>
        <div style={{ fontSize: 44, fontWeight: 700, marginTop: 18 }}>
          <MaskWords text="more real errors caught" at={246 + H} base={2} />
        </div>
        <div style={{ fontSize: 34, color: C.text, marginTop: 20, fontWeight: 600, opacity: fade(f, 276 + H, 10) }}>at similar precision<br /><span style={{ color: C.text2 }}>(0.59 vs 0.62)</span></div>
      </div>
      <div
        style={{
          position: "absolute",
          bottom: vertical ? 120 : 46,
          left: vertical ? 60 : 0,
          right: vertical ? 60 : 0,
          textAlign: "center",
          fontSize: vertical ? 28 : 26,
          lineHeight: 1.45,
          color: C.text2,
          opacity: fade(f, 84, 10),
        }}
      >
        L2-ARCTIC · Vietnamese L1 speakers · held-out speakers THV + TLV · same 100 utterances (3,200 annotated phones)
        <br />
        Baseline: Whisper-small transcript diff · SpeakLoop: wav2vec2 phone posteriors, GOP scoring
      </div>
    </Scene>
  );
};

// ---------------------------------------------------------------------------------------------
// 10. ARCHITECTURE — animated loop diagram.
const NODES = [
  { t: "Alexa+", s: "MCP host · Streamable HTTP · spec 2025‑11‑25" },
  { t: "SpeakLoop MCP", s: "9 typed tools · MCP App card · Agent Skill" },
  { t: "Phoneme GOP", s: "wav2vec2 phone posteriors → a score per sound" },
  { t: "FSRS memory", s: "spaced repetition per sound, across sessions" },
  { t: "Strands planner", s: "Strands Agents SDK · Amazon Bedrock" },
];
export const Arch: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const NW = 300,
    NH = 270,
    GAP = 60,
    X0 = (1920 - (5 * NW + 4 * GAP)) / 2,
    Y = 330;
  const cx = (i: number) => X0 + i * (NW + GAP) + NW / 2;
  // packet travels the loop from f=200
  const loopT = f >= 196 ? ((f - 196) / 150) % 1 : -1;
  const pktNode = loopT >= 0 ? Math.min(4, Math.floor(loopT * 1.25 * 5)) : -1;
  const arcD = `M ${cx(4)} ${Y + NH} C ${cx(4)} ${Y + NH + 190}, ${cx(0)} ${Y + NH + 190}, ${cx(0)} ${Y + NH}`;
  const arcP = ramp(f, 186, 230, 0, 1, inOut);
  return (
    <Scene dur={dur}>
      <div style={{ ...title, top: 90 }}>
        <MaskWords text="Under the hood" at={2} base={2} />
      </div>
      {/* connectors */}
      <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
        {NODES.slice(0, 4).map((_, i) => {
          const a = 34 + i * 30;
          const x1 = X0 + i * (NW + GAP) + NW + 6,
            x2 = x1 + GAP - 12;
          const p = ramp(f, a, a + 18);
          return (
            <g key={i}>
              <line x1={x1} y1={Y + NH / 2} x2={x1 + (x2 - x1) * p} y2={Y + NH / 2} stroke={C.text3} strokeWidth={3} />
              {p > 0.95 && <path d={`M ${x2 - 10} ${Y + NH / 2 - 8} L ${x2} ${Y + NH / 2} L ${x2 - 10} ${Y + NH / 2 + 8}`} stroke={C.text3} strokeWidth={3} fill="none" />}
            </g>
          );
        })}
        <path d={arcD} stroke={C.accent} strokeWidth={3} fill="none" strokeDasharray="2000" strokeDashoffset={2000 * (1 - arcP)} opacity={0.9} />
        {loopT >= 0.8 && (() => {
          // packet on the return arc
          const u = (loopT - 0.8) / 0.2;
          const bx = (t: number, a: number, b: number, c: number, d: number) =>
            (1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t ** 3 * d;
          const x = bx(u, cx(4), cx(4), cx(0), cx(0));
          const y = bx(u, Y + NH, Y + NH + 190, Y + NH + 190, Y + NH);
          return <circle cx={x} cy={y} r={12} fill={C.accent} />;
        })()}
              </svg>
      <div style={{ position: "absolute", top: Y + NH + 150, left: 0, right: 0, textAlign: "center", fontSize: 28, color: C.accentInk, fontWeight: 700, opacity: fade(f, 214, 8) }}>
        today’s plan, back to Alexa+
      </div>
      {NODES.map((n, i) => {
        const a = 20 + i * 30;
        const hot = pktNode === i && loopT < 0.8;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: X0 + i * (NW + GAP),
              top: Y,
              width: NW,
              height: NH,
              boxSizing: "border-box",
              borderRadius: 26,
              background: C.inner,
              border: `2.5px solid ${hot ? C.accent : C.line}`,
              padding: 28,
              opacity: fade(f, a, 6),
              transform: `translateY(${ramp(f, a, a + 22, 50, 0)}px)`,
            }}
          >
            <div style={{ fontSize: 22, color: C.text3, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>0{i + 1}</div>
            <div style={{ fontSize: 36, fontWeight: 700, marginTop: 10, letterSpacing: "-0.01em" }}>{n.t}</div>
            <div style={{ fontSize: 23, color: C.text2, marginTop: 12, lineHeight: 1.32 }}>{n.s}</div>
          </div>
        );
      })}
      <div style={{ position: "absolute", bottom: 100, left: 0, right: 0, textAlign: "center", fontSize: 60, fontWeight: 700, letterSpacing: "-0.02em" }}>
        <MaskWords text="Hear → score → remember → plan." at={280} base={3} />
      </div>
    </Scene>
  );
};

// ---------------------------------------------------------------------------------------------
// 11. OPEN SOURCE — mcp-lite-browser.
export const OSS: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const v = ramp(f, 12, 64) * 8.6;
  return (
    <Scene dur={dur}>
      <AbsoluteFill style={{ ...center, flexDirection: "column" }}>
        <div style={{ fontSize: 40, color: C.text2, fontWeight: 600 }}>
          <Mask at={2}>Open source, too</Mask>
        </div>
        <div style={{ fontSize: 280, fontWeight: 800, letterSpacing: "-0.05em", lineHeight: 1.05, fontVariantNumeric: "tabular-nums", opacity: fade(f, 10, 6) }}>
          {v.toFixed(1)}
          <span style={{ color: C.text2, fontSize: 160 }}> kB</span>
        </div>
        <div style={{ fontSize: 60, fontWeight: 700, color: C.accent, letterSpacing: "-0.02em" }}>
          <Mask at={40}>mcp-lite-browser</Mask>
        </div>
        <div style={{ fontSize: 36, color: C.text2, marginTop: 24, opacity: fade(f, 60, 8) }}>
          The MCP client for any web page. Streamable HTTP, OAuth 2.1, MCP Apps host.
        </div>
        <div style={{ fontSize: 30, color: C.text3, marginTop: 16, opacity: fade(f, 74, 8) }}>
          Zero dependencies · min+gzip · MIT · github.com/ducvuathuduc/mcp-lite-browser
        </div>
      </AbsoluteFill>
    </Scene>
  );
};

// ---------------------------------------------------------------------------------------------
// 12. CLOSE — boring on purpose: name, line, URL, held.
export const Close: React.FC<{ dur: number; vertical?: boolean }> = ({ dur, vertical }) => {
  const f = useCurrentFrame();
  return (
    <Scene dur={dur} exit={18}>
      <AbsoluteFill style={{ ...center, flexDirection: "column", gap: 0 }}>
        <Lockup at={0} size={vertical ? 120 : 150} />
        <div style={{ fontSize: vertical ? 50 : 56, color: C.text2, marginTop: 50, fontWeight: 500 }}>
          <MaskWords text="Speak a little every day." at={vertical ? 12 : 24} base={2} />
        </div>
        <div
          style={{
            marginTop: 80,
            padding: vertical ? "20px 34px" : "22px 44px",
            borderRadius: 999,
            border: `2px solid ${C.line}`,
            fontSize: vertical ? 38 : 46,
            fontWeight: 700,
            opacity: fade(f, vertical ? 24 : 50, 8),
            transform: `translateY(${ramp(f, vertical ? 24 : 50, vertical ? 48 : 76, 30, 0)}px)`,
          }}
        >
          github.com/ducvuathuduc/speakloop
        </div>
        <div style={{ fontSize: vertical ? 26 : 26, color: C.text3, marginTop: 40, opacity: fade(f, vertical ? 36 : 74, 10), padding: vertical ? "0 60px" : 0 }}>
          Built for Alexa+ · MCP 2025-11-25 · Amazon Bedrock · open source
        </div>
      </AbsoluteFill>
    </Scene>
  );
};
