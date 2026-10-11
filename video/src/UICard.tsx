import React from "react";
import "./ui/tokens.css";
import "./ui/styles.css";
// @ts-ignore vendored Preact card set (scripts/vendor_ui.py)
import { DrillCard, KaraokeCard, ListenCard, RingsCard, SplitCard } from "./ui/cards.jsx";
// @ts-ignore
import { FIXTURES } from "./ui/fixtures.js";

export const BASE_W = 768;
export const BASE_H = 480;
export type UIState =
  | { kind: "listen"; rec?: { state: string; level?: number } }
  | { kind: "split"; playing?: string | null }
  | { kind: "karaoke"; t: number | null; playing?: boolean; source?: "yours" | "target" }
  | { kind: "drill"; rec?: { state: string; level?: number }; last?: { word: string; ok: boolean; note: string }; step?: number; secondsLeft?: number }
  | { kind: "rings" };

const noop = () => {};

/** The real SpeakLoop card (feat/ui components), laid out at the 768x480 base canvas times `zoom`. */
export const UICard: React.FC<{ s: UIState; zoom: number; style?: React.CSSProperties }> = ({ s, zoom, style }) => {
  let card: React.ReactNode = null;
  const a = FIXTURES.assessment;
  if (s.kind === "listen") card = <ListenCard d={FIXTURES.listen} rec={s.rec || { state: "idle" }} onMic={noop} onRetry={noop} />;
  if (s.kind === "split") card = <SplitCard a={a} playing={s.playing ?? null} onYours={noop} onTarget={noop} onDetails={noop} onPractise={noop} />;
  if (s.kind === "karaoke")
    card = <KaraokeCard a={a} t={s.t} playing={!!s.playing} source={s.source || "yours"} onToggle={noop} onSource={noop} onBack={noop} />;
  if (s.kind === "drill") {
    const d = {
      ...FIXTURES.drill,
      step: s.step ?? FIXTURES.drill.step,
      seconds_left: s.secondsLeft ?? FIXTURES.drill.seconds_left,
      last_attempt: s.last ?? FIXTURES.drill.last_attempt,
    };
    card = <DrillCard d={d} rec={s.rec || { state: "idle" }} onMic={noop} />;
  }
  if (s.kind === "rings") card = <RingsCard data={FIXTURES.rings} onStart={noop} />;
  return (
    <div className="slui" style={{ width: BASE_W * zoom, height: BASE_H * zoom, ...style }}>
      <div className="surface" style={{ zoom, height: BASE_H }}>
        {card}
      </div>
    </div>
  );
};
