import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  continueRender,
  delayRender,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

// ---- Design tokens (speakloop-ui/ui/src/tokens.css, dark theme) ------------------------
export const C = {
  bg: "#0B0D11",
  card: "#14181E",
  inner: "#1B2028",
  line: "#2A313C",
  track: "#262D38",
  text: "#F3F5F8",
  text2: "#A9B2C0",
  text3: "#8892A1",
  accent: "#FF8A3D",
  accentInk: "#FFA466",
  onAccent: "#1A1007",
  ok: "#56B4E9",
  changed: "#F0E442",
  missing: "#E59BC8",
  btn: "#2D415E",
};
export const FONT = '"Atkinson Hyperlegible Next", "Noto Sans", system-ui, sans-serif';
export const PHON = '"SpeakLoop Phonetic", "Charis SIL", "Noto Serif", serif';

// ---- Fonts ------------------------------------------------------------------------------
let fontsRequested = false;
export const useFonts = () => {
  if (fontsRequested || typeof document === "undefined") return;
  fontsRequested = true;
  const handle = delayRender("fonts");
  const faces = [
    new FontFace("Atkinson Hyperlegible Next", `url(${staticFile("atkinson-next-latin.woff2")})`, {
      weight: "200 800",
      unicodeRange:
        "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD",
    }),
    new FontFace("Atkinson Hyperlegible Next", `url(${staticFile("atkinson-next-latin-ext.woff2")})`, {
      weight: "200 800",
      unicodeRange: "U+0100-024F",
    }),
    new FontFace("SpeakLoop Phonetic", `url(${staticFile("speakloop-phonetic.woff2")})`, { weight: "400" }),
  ];
  Promise.all(faces.map((f) => f.load()))
    .then((loaded) => {
      loaded.forEach((f) => document.fonts.add(f));
      return document.fonts.ready;
    })
    .then(() => continueRender(handle))
    .catch((e) => {
      console.error(e);
      continueRender(handle);
    });
};

// ---- Motion -----------------------------------------------------------------------------
export const expoOut = Easing.bezier(0.16, 1, 0.3, 1);
export const quintIn = Easing.bezier(0.7, 0, 0.84, 0);
export const inOut = Easing.bezier(0.65, 0, 0.35, 1);

export const ramp = (f: number, a: number, b: number, from = 0, to = 1, easing = expoOut) =>
  interpolate(f, [a, b], [from, to], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing });

/** opacity on a short ramp, separate from the transform curve */
export const fade = (f: number, start: number, len = 6) => ramp(f, start, start + len, 0, 1, Easing.quad);

export const stagger = (i: number, base: number) => Math.round(base * Math.pow(i, 0.8));

/** visibility window: 1 inside [inF, outF], eased out over `len` frames after outF */
export const exitK = (f: number, outF: number, len = 10) => ramp(f, outF, outF + len, 0, 1, quintIn);

// ---- Masked text reveal ------------------------------------------------------------------
type MaskProps = {
  children: React.ReactNode;
  at: number;
  out?: number;
  dur?: number;
  style?: React.CSSProperties;
  dir?: 1 | -1;
};
export const Mask: React.FC<MaskProps> = ({ children, at, out, dur = 22, style, dir = 1 }) => {
  const f = useCurrentFrame();
  const y = ramp(f, at, at + dur, 105 * dir, 0);
  const o = fade(f, at, 5);
  const x = out !== undefined ? exitK(f, out, 12) : 0;
  return (
    <span style={{ display: "inline-block", overflow: "hidden", verticalAlign: "bottom", paddingBottom: "0.08em", marginBottom: "-0.08em", ...style }}>
      <span style={{ display: "inline-block", transform: `translateY(${y - x * 105}%)`, opacity: o * (1 - x * 0.2) }}>{children}</span>
    </span>
  );
};

/** Words revealed one by one behind masks; `color` map lets single words take the accent. */
export const MaskWords: React.FC<{
  text: string;
  at: number;
  out?: number;
  base?: number;
  style?: React.CSSProperties;
  colors?: Record<number, string>;
}> = ({ text, at, out, base = 3, style, colors = {} }) => {
  const words = text.split(" ");
  return (
    <span style={style}>
      {words.map((w, i) => (
        <React.Fragment key={i}>
          <Mask at={at + stagger(i, base)} out={out !== undefined ? out + stagger(i, 1.5) : undefined}>
            <span style={{ color: colors[i] }}>{w}</span>
          </Mask>
          {i < words.length - 1 ? " " : null}
        </React.Fragment>
      ))}
    </span>
  );
};

// ---- Stage ------------------------------------------------------------------------------
export const Stage: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  const f = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const gx = 50 + 18 * Math.sin(f / 260);
  const gy = 42 + 10 * Math.cos(f / 310);
  return (
    <AbsoluteFill style={{ backgroundColor: C.bg, fontFamily: FONT, color: C.text }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse 60% 55% at ${gx}% ${gy}%, rgba(45,65,94,0.35), rgba(11,13,17,0) 70%)`,
        }}
      />
      {children}
      <AbsoluteFill
        style={{
          background: "radial-gradient(ellipse 85% 80% at 50% 50%, rgba(0,0,0,0) 60%, rgba(0,0,0,0.55) 100%)",
          pointerEvents: "none",
        }}
      />
      <AbsoluteFill
        style={{
          backgroundImage: `url(${staticFile("grain.png")})`,
          backgroundPosition: `${(f * 137) % 512}px ${(f * 251) % 512}px`,
          opacity: 0.05,
          mixBlendMode: "overlay",
          pointerEvents: "none",
          width,
          height,
        }}
      />
    </AbsoluteFill>
  );
};

/** Scene wrapper: settles out (shrink + fade as one group) over the last frames. */
export const Scene: React.FC<{ dur: number; children: React.ReactNode; exit?: number; style?: React.CSSProperties }> = ({
  dur,
  children,
  exit = 9,
  style,
}) => {
  const f = useCurrentFrame();
  const k = exitK(f, dur - exit, exit);
  return (
    <AbsoluteFill style={{ opacity: 1 - k, transform: `scale(${1 - 0.04 * k})`, ...style }}>{children}</AbsoluteFill>
  );
};

export const Logo: React.FC<{ size: number; style?: React.CSSProperties }> = ({ size, style }) => (
  <Img src={staticFile("logo.svg")} style={{ width: size, height: size, display: "block", ...style }} />
);

export const Chip: React.FC<{ children: React.ReactNode; color?: string; style?: React.CSSProperties }> = ({
  children,
  color = C.text2,
  style,
}) => (
  <span
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 10,
      padding: "8px 18px",
      borderRadius: 999,
      border: `1.5px solid ${C.line}`,
      color,
      fontSize: 26,
      fontWeight: 500,
      ...style,
    }}
  >
    {children}
  </span>
);

/** 3D device frame for real screenshots / footage */
export const Frame3D: React.FC<{
  children: React.ReactNode;
  w: number;
  h: number;
  rx: number;
  ry: number;
  rz?: number;
  s?: number;
  tx?: number;
  ty?: number;
  o?: number;
}> = ({ children, w, h, rx, ry, rz = 0, s = 1, tx = 0, ty = 0, o = 1 }) => (
  <AbsoluteFill style={{ perspective: 2400, alignItems: "center", justifyContent: "center" }}>
    <div
      style={{
        width: w,
        height: h,
        transform: `translate(${tx}px, ${ty}px) rotateX(${rx}deg) rotateY(${ry}deg) rotateZ(${rz}deg) scale(${s})`,
        transformStyle: "preserve-3d",
        borderRadius: 28,
        overflow: "hidden",
        boxShadow: "0 60px 140px rgba(0,0,0,0.65), 0 0 0 1.5px rgba(255,255,255,0.08)",
        opacity: o,
      }}
    >
      {children}
    </div>
  </AbsoluteFill>
);
