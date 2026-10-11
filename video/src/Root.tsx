import React from "react";
import { AbsoluteFill, Audio, Composition, Img, Sequence, interpolate, staticFile } from "remotion";
import { C, Frame3D, Stage, Scene, useFonts, MaskWords, fade, ramp } from "./lib";
import { Drill, Hears, Hook, Karaoke, Lockup, Problem, Reveal } from "./scenesA";
import { Arch, Close, Memory, OSS, Proof } from "./scenesB";
import { Real } from "./sceneReal";
import { UICard } from "./UICard";
import { useCurrentFrame } from "remotion";
import { Measure } from "./Measure";

// Scene boundaries in frames (30 fps). Every boundary is a multiple of 60 = one bar at 120 BPM,
// so cuts land on the downbeat of the synthesized score (src/music_sections.json).
export const TIMELINE: [string, number, React.FC<{ dur: number }>][] = [
  ["hook", 180, Hook],
  ["problem", 240, Problem],
  ["reveal", 240, Reveal],
  ["hears", 420, Hears],
  ["karaoke", 360, Karaoke],
  ["drill", 300, Drill],
  ["memory", 300, Memory],
  ["real", 600, Real],
  ["proof", 480, Proof],
  ["arch", 420, Arch],
  ["oss", 240, OSS],
  ["close", 360, Close],
];
const TOTAL = TIMELINE.reduce((a, [, d]) => a + d, 0);

const Launch: React.FC = () => {
  useFonts();
  let at = 0;
  return (
    <Stage>
      {TIMELINE.map(([name, dur, S]) => {
        const from = at;
        at += dur;
        return (
          <Sequence key={name} name={name} from={from} durationInFrames={dur}>
            <S dur={dur} />
          </Sequence>
        );
      })}
      {/* music + voice, mixed and ducked by scripts/mix_audio.py */}
      <Audio src={staticFile("mix_launch.wav")} />
    </Stage>
  );
};

// ---- 32 s vertical teaser -------------------------------------------------------------------
const TeaserCard: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const p = ramp(f, 0, 40);
  return (
    <Scene dur={dur}>
      <div style={{ position: "absolute", top: 220, left: 0, right: 0, textAlign: "center", fontSize: 76, fontWeight: 700, letterSpacing: "-0.03em", padding: "0 70px" }}>
        <MaskWords text="Hears every sound, not just the words." at={4} base={2} colors={{ 2: C.accent }} />
      </div>
      <Frame3D w={1280} h={800} rx={interpolate(p, [0, 1], [24, 8])} ry={interpolate(p, [0, 1], [-26, -10])} s={interpolate(p, [0, 1], [0.6, 0.78])} ty={interpolate(p, [0, 1], [400, 120])} o={fade(f, 0, 6)}>
        <UICard s={{ kind: "split" }} zoom={1280 / 768} />
      </Frame3D>
      <div style={{ position: "absolute", bottom: 300, left: 0, right: 0, textAlign: "center", fontSize: 50, fontWeight: 700, padding: "0 80px" }}>
        <MaskWords text="The /t/ in “walked” went missing." at={60} base={2} colors={{ 1: C.missing }} />
      </div>
    </Scene>
  );
};
const TeaserReveal: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 60 }}>
      <Lockup at={0} size={130} />
      <div style={{ fontSize: 52, color: C.text2, textAlign: "center", padding: "0 90px", lineHeight: 1.3 }}>
        <MaskWords text="The speaking coach for Alexa+ that hears every sound." at={30} base={2} />
      </div>
    </AbsoluteFill>
  </Scene>
);
const TEASER: [string, number, React.FC<{ dur: number }>][] = [
  ["hook", 180, (p) => <Hook {...p} vertical />],
  ["reveal", 120, TeaserReveal],
  ["card", 180, TeaserCard],
  ["proof", 300, (p) => <Proof {...p} vertical />],
  ["close", 180, (p) => <Close {...p} vertical />],
];
const TEASER_TOTAL = TEASER.reduce((a, [, d]) => a + d, 0);
const Teaser: React.FC = () => {
  useFonts();
  let at = 0;
  return (
    <Stage>
      {TEASER.map(([name, dur, S]) => {
        const from = at;
        at += dur;
        return (
          <Sequence key={name} name={name} from={from} durationInFrames={dur}>
            <S dur={dur} />
          </Sequence>
        );
      })}
      <Audio src={staticFile("mix_teaser.wav")} />
    </Stage>
  );
};

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="Launch" component={Launch} durationInFrames={TOTAL} fps={30} width={1920} height={1080} />
    <Composition id="Measure" component={Measure} durationInFrames={1} fps={30} width={1600} height={1040} />
    <Composition id="Teaser" component={Teaser} durationInFrames={TEASER_TOTAL} fps={30} width={1080} height={1920} />
  </>
);
