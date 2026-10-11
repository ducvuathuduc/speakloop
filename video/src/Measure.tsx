import React, { useEffect } from "react";
import { AbsoluteFill, continueRender, delayRender } from "remotion";
import { UICard, UIState } from "./UICard";
import { useFonts } from "./lib";
const STATES: UIState[] = [{ kind: "listen" }, { kind: "split" }, { kind: "karaoke", t: null }, { kind: "drill" }];
const SEL = [".mic-btn", ".btn-ghost", ".btn-round", ".segmented button", ".pane-sl", ".pane-typical", ".mini-strip", ".btn-primary", ".strip", ".headline", ".target-sentence", ".pairs", ".last", ".now", ".verdict", ".card-head"];
export const Measure: React.FC = () => {
  useFonts();
  useEffect(() => {
    const h = delayRender("measure");
    document.fonts.ready.then(() => setTimeout(() => {
      const out: Record<string, unknown> = {};
      document.querySelectorAll("[data-m]").forEach((root) => {
        const r0 = root.getBoundingClientRect();
        const k = (root as HTMLElement).dataset.m!;
        out[k] = Object.fromEntries(SEL.map((s) => [s, Array.from(root.querySelectorAll(s)).map((e) => { const r = e.getBoundingClientRect(); return [Math.round(r.x - r0.x), Math.round(r.y - r0.y), Math.round(r.width), Math.round(r.height)]; })]).filter(([, v]) => (v as unknown[]).length));
      });
      console.log("MEASURE " + JSON.stringify(out));
      continueRender(h);
    }, 500));
  }, []);
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      {STATES.map((s, i) => (
        <div key={i} data-m={s.kind} style={{ position: "absolute", left: (i % 2) * 800, top: Math.floor(i / 2) * 520 }}>
          <UICard s={s} zoom={1} />
        </div>
      ))}
    </AbsoluteFill>
  );
};
