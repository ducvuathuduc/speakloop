import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, Chip, FONT, Frame3D, Logo, Mask, MaskWords, PHON, Scene, exitK, expoOut, fade, inOut, ramp, stagger } from "./lib";

const center: React.CSSProperties = { alignItems: "center", justifyContent: "center", textAlign: "center" };

// deterministic pseudo-random
const rnd = (i: number) => {
  const x = Math.sin(i * 12.9898) * 43758.5453;
  return x - Math.floor(x);
};

export const Wave: React.FC<{ from: number; to: number; bars?: number; color?: string; h?: number; w?: number }> = ({
  from,
  to,
  bars = 36,
  color = C.text2,
  h = 90,
  w = 520,
}) => {
  const f = useCurrentFrame();
  const active = f >= from && f <= to;
  const k = ramp(f, from, from + 6) * (1 - ramp(f, to - 6, to));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: (w - bars * 6) / (bars - 1), height: h, width: w }}>
      {new Array(bars).fill(0).map((_, i) => {
        const v = active ? 0.15 + 0.85 * Math.abs(Math.sin(f * 0.55 + i * 0.7) * rnd(i + Math.floor(f / 2) * 31)) : 0.06;
        return <div key={i} style={{ width: 6, height: Math.max(6, h * v * Math.max(k, 0.07)), borderRadius: 3, background: color }} />;
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------------------------
// 1. HOOK — split screen: you said "walk", speech recognition heard "walked".
export const Hook: React.FC<{ dur: number; vertical?: boolean }> = ({ dur, vertical }) => {
  const f = useCurrentFrame();
  const line = ramp(f, 0, 18);
  const word = (txt: string, at: number, color: string) => (
    <div style={{ fontSize: vertical ? 190 : 210, fontWeight: 700, letterSpacing: "-0.035em", lineHeight: 1, color }}>
      <Mask at={at} dur={20}>
        <span>“{txt}”</span>
      </Mask>
    </div>
  );
  const half = (side: "L" | "R"): React.CSSProperties =>
    vertical
      ? { position: "absolute", left: 0, right: 0, top: side === "L" ? 260 : 1010, height: 620, ...center, display: "flex", flexDirection: "column", gap: 34 }
      : { position: "absolute", top: 60, bottom: 200, width: 960, left: side === "L" ? 0 : 960, display: "flex", flexDirection: "column", ...center, gap: 34 };
  const capAt = 112;
  return (
    <Scene dur={dur}>
      {/* divider */}
      <div
        style={
          vertical
            ? { position: "absolute", top: 960, left: 140, height: 2, width: 800 * line, background: C.line }
            : { position: "absolute", left: 959, top: 170, width: 2, height: 640 * line, background: C.line }
        }
      />
      <div style={half("L")}>
        <div style={{ fontSize: 40, color: C.text2, fontWeight: 600 }}>
          <Mask at={4}>You said</Mask>
        </div>
        {word("walk", 10, C.text)}
        <div style={{ opacity: fade(f, 8, 8) }}>
          <Wave from={10} to={100} color={C.text2} w={vertical ? 560 : 520} />
        </div>
        <div style={{ fontSize: 32, color: C.text3, opacity: fade(f, 20, 10) }}>She walk to the shops yesterday.</div>
      </div>
      <div style={half("R")}>
        <div style={{ fontSize: 40, color: C.text2, fontWeight: 600 }}>
          <Mask at={34}>Speech recognition heard</Mask>
        </div>
        {word("walked", 42, C.text)}
        <div
          style={{
            height: 90,
            display: "flex",
            alignItems: "center",
            opacity: fade(f, 62, 6),
            transform: `translateY(${ramp(f, 62, 84, 24, 0)}px)`,
          }}
        >
          <span style={{ fontSize: 44, fontWeight: 700, color: C.ok }}>✓ Looks perfect</span>
        </div>
        <div style={{ fontSize: 32, color: C.text3, opacity: fade(f, 50, 10) }}>She walked to the shops yesterday.</div>
      </div>
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: vertical ? 150 : 96,
          textAlign: "center",
          fontSize: vertical ? 54 : 60,
          fontWeight: 700,
          letterSpacing: "-0.02em",
          padding: vertical ? "0 80px" : 0,
        }}
      >
        <MaskWords text="It fixed your mistake. And never told you." at={capAt} base={3} colors={{ 5: C.accent, 6: C.accent, 7: C.accent }} />
      </div>
    </Scene>
  );
};

// ---------------------------------------------------------------------------------------------
// 2. PROBLEM — kinetic type, one line per beat-pair.
export const Problem: React.FC<{ dur: number }> = ({ dur }) => {
  const big: React.CSSProperties = { fontSize: 104, fontWeight: 700, letterSpacing: "-0.03em", lineHeight: 1.08, maxWidth: 1500 };
  return (
    <Scene dur={dur} exit={1}>
      <AbsoluteFill style={center}>
        <div style={big}>
          <MaskWords text="Speech recognition is built to forgive." at={2} out={58} />
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={center}>
        <div style={big}>
          <MaskWords text="It hears the word you meant." at={72} out={128} />
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{ ...center, flexDirection: "column", gap: 10 }}>
        <div style={{ ...big, color: C.text2 }}>
          <MaskWords text="Great for commands." at={140} out={208} />
        </div>
        <div style={big}>
          <MaskWords text="Useless for learning to speak." at={158} out={210} colors={{ 2: C.accent, 3: C.accent, 4: C.accent }} />
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={center}>
        <div style={big}>
          <MaskWords text="A coach has to hear what you actually said." at={224} out={288} />
        </div>
      </AbsoluteFill>
    </Scene>
  );
};

// ---------------------------------------------------------------------------------------------
// 3. REVEAL — logo lockup, then the real card on a tilted frame + the headline claim.
export const Lockup: React.FC<{ at: number; size?: number; out?: number }> = ({ at, size = 150, out }) => {
  const f = useCurrentFrame();
  const s = ramp(f, at, at + 26, 0.55, 1);
  const r = ramp(f, at, at + 30, -14, 0);
  const x = out !== undefined ? exitK(f, out, 12) : 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: size * 0.26 }}>
      <div style={{ transform: `scale(${s * (1 - 0.3 * x)}) rotate(${r}deg)`, opacity: fade(f, at, 5) * (1 - x) }}>
        <Logo size={size * 1.05} style={{ borderRadius: size * 0.24 }} />
      </div>
      <div style={{ fontSize: size, fontWeight: 700, letterSpacing: "-0.035em", lineHeight: 1 }}>
        <Mask at={at + 8} out={out} dur={24}>
          SpeakLoop
        </Mask>
      </div>
    </div>
  );
};

export const Reveal: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const p = ramp(f, 120, 168);
  const drift = interpolate(f, [168, dur], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <Scene dur={dur}>
      <AbsoluteFill style={{ ...center, flexDirection: "column", gap: 54 }}>
        <Lockup at={0} out={112} />
        <div style={{ fontSize: 50, color: C.text2, fontWeight: 500 }}>
          <MaskWords text="The speaking coach for Alexa+ that hears every sound." at={36} out={110} base={2} />
        </div>
      </AbsoluteFill>
      {f >= 118 && (
        <>
          <Frame3D
            w={1280}
            h={800}
            rx={interpolate(p, [0, 1], [26, 9]) - 3 * drift}
            ry={interpolate(p, [0, 1], [-30, -11]) + 4 * drift}
            rz={interpolate(p, [0, 1], [4, 1])}
            s={interpolate(p, [0, 1], [0.7, 0.9]) + 0.02 * drift}
            ty={interpolate(p, [0, 1], [420, 60])}
            o={fade(f, 118, 6)}
          >
            <Img src={staticFile("assessment-dark-1280x800.png")} style={{ width: 1280, height: 800 }} />
          </Frame3D>
          <div style={{ position: "absolute", top: 70, left: 0, right: 0, textAlign: "center", fontSize: 54, fontWeight: 700, letterSpacing: "-0.02em" }}>
            <MaskWords text="Finds 2.4× more real pronunciation errors than a transcript check." at={150} base={2} colors={{ 1: C.accent }} />
          </div>
          <div style={{ position: "absolute", bottom: 34, left: 0, right: 0, textAlign: "center", fontSize: 26, color: C.text2, opacity: fade(f, 175, 10) }}>
            Recall 0.53 vs 0.22 · L2-ARCTIC, Vietnamese L1 speakers · details at 1:20
          </div>
        </>
      )}
    </Scene>
  );
};

// ---------------------------------------------------------------------------------------------
// 4. HEARS — the assessment card rebuilt live: transcript check vs SpeakLoop, punch-in on /t/.
const Underline: React.FC<{ at: number; color: string; wavy?: boolean; children: React.ReactNode; mark: string }> = ({
  at,
  color,
  wavy,
  children,
  mark,
}) => {
  const f = useCurrentFrame();
  const w = ramp(f, at, at + 16) * 100;
  return (
    <span style={{ position: "relative", display: "inline-block", marginRight: "0.42em" }}>
      {children}
      <span
        style={{
          position: "absolute",
          left: 0,
          bottom: -6,
          height: wavy ? 10 : 5,
          width: `${w}%`,
          borderRadius: 3,
          background: wavy
            ? `radial-gradient(circle at 50% 0, transparent 4px, ${color} 4px, ${color} 6px, transparent 6px) 0 0 / 14px 10px repeat-x`
            : color,
        }}
      />
      <span style={{ position: "absolute", right: -26, top: -14, fontSize: 30, color, opacity: fade(f, at + 10, 6) }}>{mark}</span>
    </span>
  );
};

export const Tiles: React.FC<{ at: number; size?: number }> = ({ at, size = 104 }) => {
  const f = useCurrentFrame();
  const ph = ["w", "ɔː", "k", "t"];
  return (
    <div style={{ display: "flex", gap: size * 0.16 }}>
      {ph.map((p, i) => {
        const a = at + stagger(i, 6);
        const miss = i === 3;
        return (
          <div
            key={i}
            style={{
              position: "relative",
              width: size,
              height: size,
              borderRadius: size * 0.16,
              background: miss ? "transparent" : "#0F1217",
              border: miss ? `3px solid ${C.missing}` : "3px solid transparent",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontFamily: PHON,
              fontSize: size * 0.5,
              color: miss ? C.text3 : C.text,
              opacity: fade(f, a, 5),
              transform: `translateY(${ramp(f, a, a + 18, 30, 0)}px)`,
            }}
          >
            {p}
            {miss && (
              <span
                style={{
                  position: "absolute",
                  right: -14,
                  top: -14,
                  width: 36,
                  height: 36,
                  borderRadius: 18,
                  background: C.card,
                  color: C.missing,
                  fontSize: 24,
                  fontFamily: FONT,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transform: `scale(${ramp(f, a + 10, a + 24, 0, 1)})`,
                }}
              >
                ∅
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
};

export const Hears: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const card: React.CSSProperties = {
    position: "absolute",
    top: 210,
    width: 840,
    height: 560,
    borderRadius: 32,
    background: C.inner,
    padding: 52,
    display: "flex",
    flexDirection: "column",
    boxSizing: "border-box",
  };
  const zIn = ramp(f, 150, 196, 0, 1, inOut);
  const zOut = ramp(f, 262, 300, 0, 1, inOut);
  const z = zIn * (1 - zOut);
  const scale = 1 + 0.75 * z;
  // punch-in toward the phone tiles (right card, lower half)
  const ox = 1560,
    oy = 760;
  const cardsIn = (i: number) => ({
    opacity: fade(f, 4 + i * 6, 6),
    transform: `translateY(${ramp(f, 4 + i * 6, 34 + i * 6, 70, 0)}px)`,
  });
  const dim = ramp(f, 296, 316, 1, 0);
  return (
    <Scene dur={dur}>
      <div style={{ position: "absolute", top: 82, left: 0, right: 0, textAlign: "center", fontSize: 50, fontWeight: 700, letterSpacing: "-0.02em" }}>
        <MaskWords text="Same sentence. Two ways of listening." at={2} out={140} base={2} />
      </div>
      <AbsoluteFill style={{ transform: `scale(${scale})`, transformOrigin: `${ox}px ${oy}px`, opacity: dim }}>
        <div style={{ ...card, left: 90, ...cardsIn(0), opacity: fade(f, 4, 6) * (1 - z) }}>
          <div style={{ fontSize: 30, color: C.text2, fontWeight: 600 }}>A transcript check hears</div>
          <div style={{ fontSize: 56, color: C.text2, lineHeight: 1.3, marginTop: 34, opacity: fade(f, 30, 10) }}>
            She walked to the shops yesterday.
          </div>
          <div style={{ marginTop: "auto", display: "flex", alignItems: "baseline", gap: 30, opacity: fade(f, 70, 8) }}>
            <span style={{ fontSize: 66, fontWeight: 700 }}>walked</span>
            <span style={{ fontSize: 40, fontWeight: 700, color: C.ok }}>✓ Looks perfect</span>
          </div>
        </div>
        <div style={{ ...card, left: 990, ...cardsIn(1) }}>
          <div style={{ fontSize: 30, color: C.accentInk, fontWeight: 600 }}>SpeakLoop hears</div>
          <div style={{ fontSize: 56, lineHeight: 1.45, marginTop: 30, opacity: fade(f, 40, 10) }}>
            She{" "}
            <Underline at={64} color={C.missing} mark="∅">
              walked
            </Underline>
            {"  "}to{" "}
            <Underline at={76} color={C.changed} wavy mark="≈">
              the
            </Underline>
            {"  "}
            <Underline at={88} color={C.missing} mark="∅">
              shops
            </Underline>
            {"  "}yesterday.
          </div>
          <div style={{ marginTop: "auto", display: "flex", alignItems: "center", gap: 30 }}>
            <Tiles at={100} size={96} />
            <div style={{ opacity: fade(f, 130, 8) }}>
              <div style={{ fontFamily: PHON, fontSize: 44 }}>/wɔːk/</div>
              <div style={{ fontSize: 28, color: C.missing, fontWeight: 700 }}>final /t/ missing</div>
            </div>
          </div>
        </div>
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 0, right: 0, top: 380, textAlign: "center" }}>
        <div style={{ fontSize: 92, fontWeight: 700, letterSpacing: "-0.03em" }}>
          <MaskWords text="The /t/ in “walked” went missing." at={312} base={2} colors={{ 1: C.missing }} />
        </div>
        <div style={{ fontFamily: PHON, fontSize: 46, color: C.text2, marginTop: 26, opacity: fade(f, 336, 10) }}>
          Âm /t/ cuối trong “walked” bị mất.
        </div>
        <div style={{ fontSize: 34, color: C.text3, marginTop: 40, opacity: fade(f, 350, 10) }}>One fix, in English and Vietnamese.</div>
      </div>
    </Scene>
  );
};

// ---------------------------------------------------------------------------------------------
// 5. KARAOKE — the phoneme strip, played back.
type Ph = { p: string; st?: "miss" | "chg"; tgt?: string; note?: string };
const WORDS: { w: string; ph: Ph[] }[] = [
  { w: "She", ph: [{ p: "ʃ" }, { p: "iː" }] },
  { w: "walked", ph: [{ p: "w" }, { p: "ɔː" }, { p: "k" }, { p: "t", st: "miss" }] },
  { w: "to", ph: [{ p: "t" }, { p: "uː" }] },
  { w: "the", ph: [{ p: "d", st: "chg", tgt: "ð", note: "for ð" }, { p: "ə" }] },
  { w: "shops", ph: [{ p: "ʃ" }, { p: "ɒ" }, { p: "p" }, { p: "s", st: "miss" }] },
  { w: "yesterday", ph: [{ p: "j" }, { p: "ɛ" }, { p: "s" }, { p: "t" }, { p: "ə" }, { p: "d" }, { p: "eɪ" }] },
];

export const Karaoke: React.FC<{ dur: number; scale?: number }> = ({ dur, scale = 1 }) => {
  const f = useCurrentFrame();
  const total = WORDS.reduce((a, w) => a + w.ph.length, 0);
  const prog = ramp(f, 40, 250, 0, 1, (t) => t) * total; // linear playhead
  const target = f >= 278;
  const tog = ramp(f, 270, 286);
  let idx = 0;
  const cellW = 70;
  return (
    <Scene dur={dur}>
      <div style={{ position: "absolute", top: 110, left: 0, right: 0, textAlign: "center", fontSize: 64, fontWeight: 700, letterSpacing: "-0.025em" }}>
        <div style={{ position: "relative", height: 80 }}>
          <AbsoluteFill>
            <MaskWords text="Play it back, one sound at a time." at={2} out={262} base={2} />
          </AbsoluteFill>
          <AbsoluteFill>
            <MaskWords text="Then hear the target." at={280} base={2} colors={{ 3: C.accent }} />
          </AbsoluteFill>
        </div>
      </div>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <div style={{ transform: `scale(${scale})`, transformOrigin: "center", marginTop: 110 }}>
          {/* toggle */}
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 40, opacity: fade(f, 10, 8) }}>
            <div style={{ position: "relative", display: "flex", background: C.inner, borderRadius: 999, padding: 6 }}>
              <div
                style={{
                  position: "absolute",
                  top: 6,
                  left: 6 + tog * 128,
                  width: 128,
                  height: 52,
                  borderRadius: 999,
                  background: C.btn,
                }}
              />
              {["Yours", "Target"].map((t, i) => (
                <div key={t} style={{ position: "relative", width: 128, height: 52, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24, fontWeight: 700, color: (i === 1) === target ? C.text : C.text3 }}>
                  {t}
                </div>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", gap: 26 }}>
            {WORDS.map((wd, wi) => {
              const wordStart = idx;
              const wa = 8 + stagger(wi, 5);
              const cells = wd.ph.map((ph) => {
                const i = idx++;
                const played = prog > i;
                const active = prog > i && prog <= i + 1 && !target;
                let color = played || target ? C.text : C.text3;
                let border = "transparent";
                if (!target && played && ph.st === "miss") {
                  color = C.text3;
                  border = C.missing;
                }
                if (!target && played && ph.st === "chg") color = C.changed;
                const glyph = target && ph.tgt ? ph.tgt : ph.p;
                return (
                  <div key={i} style={{ width: cellW, display: "flex", flexDirection: "column", alignItems: "center" }}>
                    <div
                      style={{
                        fontFamily: PHON,
                        fontSize: 58,
                        height: 82,
                        width: 60,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color,
                        borderRadius: 8,
                        border: `2.5px solid ${border}`,
                        transform: `scale(${active ? 1.12 : 1})`,
                      }}
                    >
                      {glyph}
                    </div>
                    <div style={{ marginTop: 10, width: cellW - 6, height: 5, borderRadius: 3, background: active ? C.accent : played || target ? C.text3 : C.track }} />
                    <div style={{ height: 64, marginTop: 10, textAlign: "center", fontSize: 26, lineHeight: 1.1 }}>
                      {!target && played && ph.st === "miss" && <span style={{ color: C.missing, fontSize: 32 }}>∅</span>}
                      {!target && played && ph.st === "chg" && (
                        <span style={{ color: C.changed }}>
                          ≈<br />
                          <span style={{ color: C.text2, fontFamily: PHON }}>{ph.note}</span>
                        </span>
                      )}
                    </div>
                  </div>
                );
              });
              const wordActive = prog > wordStart && prog <= idx && !target;
              return (
                <div key={wi} style={{ opacity: fade(f, wa, 6), transform: `translateY(${ramp(f, wa, wa + 20, 26, 0)}px)` }}>
                  <div style={{ fontSize: 30, color: wordActive ? C.text : C.text2, fontWeight: wordActive ? 700 : 500, marginBottom: 6, paddingLeft: 4 }}>{wd.w}</div>
                  <div style={{ display: "flex" }}>{cells}</div>
                </div>
              );
            })}
          </div>
          {/* progress */}
          <div style={{ marginTop: 16, height: 5, borderRadius: 3, background: C.track, position: "relative" }}>
            <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, borderRadius: 3, width: `${(target ? 1 : prog / total) * 100}%`, background: C.accent }} />
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 40, marginTop: 34, fontSize: 28, color: C.text2, opacity: fade(f, 24, 8) }}>
            <span>
              <span style={{ color: C.ok }}>✓</span> Heard
            </span>
            <span>
              <span style={{ color: C.changed }}>≈</span> Changed
            </span>
            <span>
              <span style={{ color: C.missing }}>∅</span> Missing
            </span>
          </div>
        </div>
      </AbsoluteFill>
    </Scene>
  );
};

// ---------------------------------------------------------------------------------------------
// 6. DRILL — minimal pair + listening rings.
export const Drill: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const done = f >= 206;
  const card = (right: boolean): React.CSSProperties => ({
    position: "absolute",
    top: 270,
    left: right ? 1010 : 130,
    width: 780,
    height: 400,
    borderRadius: 32,
    background: C.inner,
    border: right ? `3px solid ${C.accent}` : "3px solid transparent",
    boxSizing: "border-box",
    padding: "70px 70px",
    opacity: fade(f, right ? 16 : 8, 6),
    transform: `translateX(${ramp(f, right ? 16 : 8, right ? 46 : 38, right ? 160 : -160, 0)}px)`,
    boxShadow: right && done ? `0 0 ${60 * ramp(f, 206, 230)}px rgba(255,138,61,0.35)` : "none",
  });
  return (
    <Scene dur={dur}>
      <div style={{ position: "absolute", top: 110, left: 0, right: 0, textAlign: "center", fontSize: 64, fontWeight: 700, letterSpacing: "-0.025em" }}>
        <MaskWords text="One fix, drilled as a minimal pair." at={2} base={2} />
      </div>
      <div style={card(false)}>
        <div style={{ fontSize: 120, fontWeight: 700, color: C.text2, letterSpacing: "-0.03em" }}>walk</div>
        <div style={{ fontFamily: PHON, fontSize: 64, color: C.text2, marginTop: 24 }}>/wɔːk/</div>
      </div>
      <div
        style={{
          position: "absolute",
          left: 930,
          top: 440,
          width: 60,
          height: 60,
          borderRadius: 30,
          border: `2px solid ${C.line}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 22,
          fontWeight: 700,
          color: C.text2,
          opacity: fade(f, 26, 6),
        }}
      >
        vs
      </div>
      <div style={card(true)}>
        <div style={{ position: "absolute", right: 40, top: 34, fontSize: 30, fontWeight: 700, color: C.accentInk }}>Say this</div>
        <div style={{ fontSize: 120, fontWeight: 700, letterSpacing: "-0.03em" }}>walked</div>
        <div style={{ fontFamily: PHON, fontSize: 64, marginTop: 24 }}>
          /wɔːk
          <span style={{ color: C.accent, borderBottom: `4px solid ${C.accent}` }}>t</span>/
        </div>
      </div>
      {/* mic + rings */}
      <div style={{ position: "absolute", top: 760, left: 0, right: 0, display: "flex", justifyContent: "center", alignItems: "center", gap: 46, opacity: fade(f, 70, 8) }}>
        <div style={{ position: "relative", width: 150, height: 150 }}>
          {!done &&
            [0, 1, 2].map((k) => {
              const ph = ((f - 90 + k * 20) % 60) / 60;
              const on = f >= 90 + 0;
              return on ? (
                <div
                  key={k}
                  style={{
                    position: "absolute",
                    inset: 0,
                    borderRadius: "50%",
                    border: `3px solid ${C.accent}`,
                    transform: `scale(${1 + ph * 1.1})`,
                    opacity: (1 - ph) * 0.6,
                  }}
                />
              ) : null;
            })}
          <div
            style={{
              position: "absolute",
              inset: 0,
              borderRadius: "50%",
              background: done ? C.ok : C.accent,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: C.onAccent,
              fontSize: 64,
              fontWeight: 800,
              transform: `scale(${done ? ramp(f, 206, 222, 0.8, 1) : 1})`,
            }}
          >
            {done ? "✓" : <MicIcon />}
          </div>
        </div>
        <div style={{ width: 620 }}>
          {!done ? (
            <>
              <div style={{ fontSize: 46, fontWeight: 700 }}>Say “walked”</div>
              <div style={{ marginTop: 14 }}>
                <Wave from={92} to={196} color={C.accentInk} h={60} w={420} bars={30} />
              </div>
            </>
          ) : (
            <>
              <div style={{ fontSize: 52, fontWeight: 700, color: C.ok }}>
                <Mask at={208}>Clear /t/.</Mask>
              </div>
              <div style={{ fontSize: 32, color: C.text2, marginTop: 10, opacity: fade(f, 220, 8) }}>Next: use it in a full sentence.</div>
            </>
          )}
        </div>
      </div>
    </Scene>
  );
};

const MicIcon = () => (
  <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke={C.onAccent} strokeWidth="2.2" strokeLinecap="round">
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
);
