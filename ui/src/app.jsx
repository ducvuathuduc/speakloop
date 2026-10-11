import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";
import { createBridge } from "./bridge.js";
import { applySurface, resolveSurface } from "./surfaces.js";
import { startRecording } from "./audio.js";
import { FIXTURES } from "./fixtures.js";
import {
  DrillCard, DrillLegacyCard, KaraokeCard, ListenCard, PlanCard, ProgressCard, ResultCard,
  ReviewCard, RingsCard, RoutineCard, SimpleCard, SplitCard,
} from "./cards.jsx";

export const ASSESS_TOOL = "assess_pronunciation";

/** Playback clock: real audio when we have the learner's recording, otherwise a timed simulation. */
function usePlayback(phones) {
  const [t, setT] = useState(null);
  const [playing, setPlaying] = useState(null);
  const raf = useRef(0);
  const audio = useRef(null);
  const stop = useCallback(() => {
    cancelAnimationFrame(raf.current);
    audio.current?.pause();
    try { window.speechSynthesis?.cancel(); } catch { /* sandbox */ }
    setPlaying(null);
  }, []);
  const play = useCallback((source, { url, text } = {}) => {
    stop();
    const first = phones?.[0]?.start ?? 0, last = phones?.[phones.length - 1]?.end ?? 2;
    setPlaying(source);
    if (source === "yours" && url) {
      const el = audio.current || (audio.current = new Audio());
      el.src = url; el.currentTime = 0; el.play().catch(() => {});
      const tick = () => { setT(el.currentTime); if (!el.paused && !el.ended) raf.current = requestAnimationFrame(tick); else setPlaying(null); };
      raf.current = requestAnimationFrame(tick);
      return;
    }
    // Target (or a fixture without audio): speak the sentence if the sandbox allows, drive the strip on a clock.
    const rate = source === "target" ? 1.25 : 1;
    if (source === "target" && text && window.speechSynthesis) {
      try { const u = new SpeechSynthesisUtterance(text); u.rate = 0.85; window.speechSynthesis.speak(u); } catch { /* sandbox */ }
    }
    const t0 = performance.now();
    const tick = () => {
      const now = first + ((performance.now() - t0) / 1000) / rate;
      setT(now);
      if (now < last + 0.2) raf.current = requestAnimationFrame(tick); else setPlaying(null);
    };
    raf.current = requestAnimationFrame(tick);
  }, [phones, stop]);
  useEffect(() => stop, [stop]);
  return { t, setT, playing, play, stop };
}

/** Recording state machine shared by the Listen and Drill cards. */
function useRecorder(bridge, { onAudio }) {
  const [rec, setRec] = useState({ state: "idle" });
  const handle = useRef(null);
  const meter = useRef(0);
  const toggle = useCallback(async () => {
    if (rec.state === "recording") {
      cancelAnimationFrame(meter.current);
      setRec({ state: "busy" });
      try {
        const out = await handle.current.stop();
        await onAudio(out);
        setRec({ state: "idle" });
      } catch (e) {
        setRec({ state: "unavailable", reason: e.reason || "unsupported" });
      }
      return;
    }
    try {
      handle.current = await startRecording();
      setRec({ state: "recording", level: 0 });
      const loop = () => { setRec((r) => (r.state === "recording" ? { ...r, level: handle.current.level() } : r)); meter.current = requestAnimationFrame(loop); };
      meter.current = requestAnimationFrame(loop);
    } catch (e) {
      setRec({ state: "unavailable", reason: e.reason || "unsupported" });
    }
  }, [rec.state, onAudio]);
  const reset = useCallback(() => setRec({ state: "idle" }), []);
  return { rec, toggle, reset };
}

export function App({ initial, params = new URLSearchParams() }) {
  const rootRef = useRef(null);
  const [data, setData] = useState(initial || null);
  const [view, setView] = useState(initial?.view || "summary");
  const [source, setSource] = useState("yours");
  const [recording, setRecording] = useState(null); // {url, wavBase64}
  const [hostCtx, setHostCtx] = useState({});
  const [displayMode, setDisplayMode] = useState("inline");

  const bridge = useMemo(() => createBridge({
    onToolResult: (r) => { if (r.structuredContent) { setData(r.structuredContent); setView(r.structuredContent.view || "summary"); } },
    onHostContext: (ctx) => setHostCtx({ ...ctx }),
  }), []);

  useEffect(() => { bridge.initialize().catch(() => {}); return () => bridge.dispose(); }, [bridge]);

  // Surface: resolve once per hostContext change -> one class + one zoom on the root.
  useEffect(() => {
    const qp = Object.fromEntries(params.entries());
    const ctx = { ...hostCtx, deviceClass: hostCtx.deviceClass || qp.device };
    const s = resolveSurface(ctx);
    if (s.warning && bridge.embedded) console.warn(`[speakloop] ${s.warning}`);
    applySurface(document.documentElement, s, hostCtx.theme || qp.theme || "dark");
    setDisplayMode(hostCtx.displayMode || qp.mode || "inline");
    document.documentElement.dataset.mode = hostCtx.displayMode || qp.mode || "inline";
  }, [hostCtx, params, bridge]);

  // Report size so inline hosts can fit the frame (ui/notifications/size-changed).
  useEffect(() => {
    if (!rootRef.current || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => bridge.sizeChanged(Math.ceil(document.documentElement.getBoundingClientRect().height)));
    ro.observe(rootRef.current);
    return () => ro.disconnect();
  }, [bridge]);

  const phones = data?.phones || [];
  const pb = usePlayback(phones);
  useEffect(() => { const t = params.get("t"); if (t != null) pb.setT(parseFloat(t)); }, []); // static frames for screenshots

  const call = useCallback(async (name, args) => {
    try {
      const r = await bridge.callTool(name, args);
      if (r?.structuredContent) { setData(r.structuredContent); setView(r.structuredContent.view || "summary"); }
      return r;
    } catch (e) { return null; }
  }, [bridge]);

  const onAudio = useCallback(async (out) => {
    setRecording(out);
    const ref = data?.reference_text;
    const r = bridge.embedded
      ? await call(ASSESS_TOOL, { reference_text: ref, audio_wav_base64: out.wavBase64, sample_rate: out.sampleRate })
      : null;
    if (!r?.structuredContent) { setData({ ...FIXTURES.assessment, reference_text: ref || FIXTURES.assessment.reference_text }); setView("summary"); }
  }, [bridge, call, data]);
  const recorder = useRecorder(bridge, { onAudio });

  const toFullscreen = async () => {
    setView("sounds");
    if (bridge.embedded && bridge.canFullscreen()) { try { await bridge.requestDisplayMode("fullscreen"); } catch { /* stay inline */ } }
  };

  if (!data) return <div ref={rootRef} class="surface"><div class="card card-empty"><p class="hint">Loading…</p></div></div>;

  let card;
  switch (data.kind) {
    case "assessment":
      card = view === "sounds" || displayMode === "fullscreen"
        ? <KaraokeCard a={data} t={pb.t} playing={!!pb.playing} source={source}
            onSource={(s) => { setSource(s); pb.stop(); }}
            onToggle={() => (pb.playing ? pb.stop() : pb.play(source, { url: recording?.url, text: data.reference_text }))}
            onBack={() => { pb.stop(); setView("summary"); if (displayMode === "fullscreen") bridge.requestDisplayMode("inline").catch(() => {}); }} />
        : <SplitCard a={data} playing={pb.playing}
            onYours={() => (pb.playing === "yours" ? pb.stop() : pb.play("yours", { url: recording?.url }))}
            onTarget={() => pb.play("target", { text: data.reference_text })}
            onDetails={toFullscreen}
            onPractise={() => call("start_pair_drill", { focus: data.l1_findings?.[0]?.rule_id })} />;
      break;
    case "sound_rings": card = <RingsCard data={data} onStart={() => call("start_pair_drill", { node: data.next_session?.node })} />; break;
    case "pair_drill": card = <DrillCard d={data} rec={recorder.rec} onMic={recorder.toggle} />; break;
    case "listen": card = <ListenCard d={data} rec={recorder.rec} onMic={recorder.toggle} onRetry={() => { recorder.reset(); setData({ ...data, mic_state: undefined }); }} />; break;
    case "plan": card = <PlanCard d={data} onStart={() => { const s = data.steps?.[0]; s?.tool === "start_sound_review" ? call("start_sound_review", {}) : call("start_drill", { task_type: s?.task_type, focus: s?.focus || undefined }); }} />; break;
    case "result": card = <ResultCard d={data} onNext={() => call("start_drill", {})} onProgress={() => call("progress_report", {})} />; break;
    case "progress": card = <ProgressCard d={data} />; break;
    case "review": card = <ReviewCard d={data} />; break;
    case "routine": card = <RoutineCard d={data} onCalendar={() => bridge.openLink(data.calendar_url).catch(() => {})} />; break;
    case "drill": card = <DrillLegacyCard d={data} />; break;
    case "tip": card = <SimpleCard title="Pronunciation tip" head={data.label} body={data.en} vi={data.vi} />; break;
    case "profile": card = <SimpleCard title="Learner" head={data.name} body={`${data.total_attempts || 0} attempts · ${data.streak_days || 0}-day streak`} />; break;
    default: card = <SimpleCard title="SpeakLoop" head={data.speech || "Ready when you are."} />;
  }
  return <div ref={rootRef} class="surface" data-kind={data.kind}>{card}</div>;
}
