// The SpeakLoop card set. Each card answers one question and maps to an Alexa+ pattern
// (Card, List, Carousel). No KPI grids, no chat bubbles, no gradients.
import { useEffect, useRef } from "preact/hooks";
import { Brand, Button, Icon, Legend, Ring, Segmented, Shell, StatusMark } from "./components.jsx";
import { activePhoneIndex, fmtClock, groupWords, headline, pct, statusOf } from "./model.js";

const firstSentence = (s) => (s ? String(s).split(/(?<=[.!?])\s/)[0] : "");
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

/* ------------------------------------------------------------------ Split: typical vs SpeakLoop */
export function SplitCard({ a, onYours, onTarget, onPractise, onDetails, playing }) {
  const words = groupWords(a);
  const h = headline(a);
  const focus = words.find((w) => w.text.toLowerCase().replace(/[^a-z']/g, "") === h.word) || words.find((w) => w.errors.length);
  const nErr = words.reduce((n, w) => n + w.errors.length, 0);
  return (
    <Shell label="What a typical assistant hears compared with what SpeakLoop hears"
      right={<>
        {a.engine === "fixture" && <span class="tag" title="Demo data, not a live assessment">Demo data</span>}
        <Button kind="ghost" icon="expand" onClick={onDetails} label={`See all ${nErr} sounds`}>{`${plural(nErr, "sound", "sounds")} to fix`}</Button>
      </>}>
      <div class="split">
        <section class="pane pane-typical" aria-label="A typical assistant hears">
          <p class="pane-label"><Icon name="ear" size={16} /> A typical assistant hears</p>
          <p class="pane-sentence">{a.asr_transcript || a.reference_text}</p>
          <p class="pane-verdict"><StatusMark type="ok" size={16} /> Looks perfect</p>
        </section>
        <section class="pane pane-sl" aria-label="SpeakLoop hears">
          <p class="pane-label"><Icon name="ear" size={16} /> SpeakLoop hears</p>
          <p class="pane-sentence">
            {words.map((w, i) => (
              <>
                <span class={w.errors.length ? `w-err w-${w.errors[0].error_type}` : "w-ok"}>
                  {w.text}{w.errors.length > 0 && <sup><StatusMark type={w.errors[0].error_type} size={14} /></sup>}
                </span>{i < words.length - 1 ? " " : ""}
              </>
            ))}
          </p>
          {focus && (
            <div class="mini-strip" aria-label={`Sounds in ${focus.text}`}>
              {focus.phones.map((p) => (
                <span class={`mini-cell s-${statusOf(p)}`}>
                  <span class="ipa">{p.error_type === "deletion" ? p.expected : p.ipa}</span>
                  {p.error_type && <StatusMark type={p.error_type} size={14} />}
                </span>
              ))}
            </div>
          )}
        </section>
      </div>
      <div class="verdict">
        <h2 class="headline">{h.en}</h2>
        {h.vi && <p class="gloss" lang="vi">{firstSentence(h.vi)}</p>}
      </div>
      <footer class="actions">
        <Button icon={playing === "yours" ? "pause" : "play"} onClick={onYours}>Yours</Button>
        <Button icon="speaker" onClick={onTarget} pressed={playing === "target"}>Target</Button>
        <span class="spacer" />
        <Button kind="primary" onClick={onPractise}>Practise this sound</Button>
      </footer>
    </Shell>
  );
}

/* ------------------------------------------------------------------ Karaoke phoneme strip */
export function KaraokeCard({ a, t, playing, source, onToggle, onSource, onBack }) {
  const words = groupWords(a);
  const flat = words.flatMap((w) => w.phones);
  const active = activePhoneIndex(flat, t);
  const end = flat.length ? flat[flat.length - 1].end : 1;
  const start = flat.length ? flat[0].start : 0;
  const progress = t == null ? 0 : Math.max(0, Math.min(1, (t - start) / (end - start)));
  const stripRef = useRef(null);
  useEffect(() => {
    const el = stripRef.current?.querySelector(".cell.active");
    el?.scrollIntoView?.({ block: "nearest", inline: "center", behavior: "smooth" });
  }, [active]);
  const activeWord = words.find((w) => w.phones.some((p) => p.index === active));
  return (
    <Shell label="Every sound, synced to your recording"
      right={<Segmented label="Audio source" value={source} onChange={onSource}
        options={[{ value: "yours", label: "Yours" }, { value: "target", label: "Target" }]} />}>
      <div class="strip" ref={stripRef} role="list" aria-label="Sounds in the sentence">
        {words.map((w) => (
          <div class={`word ${w.errors.length ? "has-err" : ""} ${activeWord === w ? "is-active" : ""}`} role="listitem">
            <span class="word-text">{w.text.replace(/[.,!?]$/, "")}</span>
            <span class="cells">
              {w.phones.map((p) => {
                const st = statusOf(p);
                const cls = p.index === active ? "active" : p.index < active ? "done" : "";
                return (
                  <span class={`cell s-${st} ${cls}`} aria-label={`${p.expected}${st === "ok" ? "" : `: ${p.error_type}${p.ipa && st === "substitution" ? `, heard ${p.ipa}` : ""}`}`}>
                    <span class="ipa">{st === "deletion" ? p.expected : p.ipa}</span>
                    <span class="tick" />
                    <span class="cell-note">{st === "ok" ? "" : <StatusMark type={st} size={14} />}{st === "substitution" ? <span class="for">for {p.expected}</span> : ""}</span>
                  </span>
                );
              })}
            </span>
          </div>
        ))}
      </div>
      <div class="timeline" aria-hidden="true"><span class="timeline-fill" style={{ width: `${progress * 100}%` }} /></div>
      <footer class="actions">
        <Button kind="ghost" icon="back" onClick={onBack} label="Back to summary" />
        <Button kind="primary" class="btn-round" icon={playing ? "pause" : "play"} onClick={onToggle} label={playing ? "Pause" : "Play with sounds"} />
        <div class="now">
          <span class="now-word">{activeWord ? activeWord.text.replace(/[.,!?]$/, "") : "Tap play"}</span>
          <span class="now-time">{fmtClock(t ?? 0)} / {fmtClock(end)}</span>
        </div>
        <span class="spacer" />
        <Legend />
      </footer>
    </Shell>
  );
}

/* ------------------------------------------------------------------ Sound rings (Carousel, 3 items) */
export function RingsCard({ data, onStart }) {
  const nodes = (data.nodes || []).slice(0, 3);
  const due = nodes.find((n) => n.due_today) || nodes[0];
  return (
    <Shell title="Your weak sounds" right={<span class="meta">{data.window_label || "This week"}</span>}>
      <ul class="rings" aria-label="Weak sounds, mastery this week">
        {nodes.map((n) => {
          const d = Math.round((n.delta_week || 0) * 100);
          return (
            <li class={`ring-item ${n === due ? "is-due" : ""}`}>
              <div class="ring-wrap">
                <Ring value={n.mastery} label={`${n.label}: ${pct(n.mastery)} percent mastered`} />
                <span class="ring-value-text">{pct(n.mastery)}<small>%</small></span>
              </div>
              <span class="ring-label">{n.label}{n === due && <span class="pill-due">Today</span>}</span>
              <span class="ring-ctx ipa">{n.context_ipa}</span>
              <span class={`trend ${d < 0 ? "down" : "up"}`}><Icon name={d < 0 ? "down" : "up"} size={16} />{`${d > 0 ? "+" : ""}${d} this week`}</span>
            </li>
          );
        })}
      </ul>
      <footer class="actions">
        <p class="next">Next: a {data.next_session?.minutes || 2}-minute warm-up on <b>{due?.label?.toLowerCase()}</b></p>
        <span class="spacer" />
        <Button kind="primary" onClick={onStart}>Start warm-up</Button>
      </footer>
    </Shell>
  );
}

/* ------------------------------------------------------------------ 2-minute minimal-pair drill */
export function DrillCard({ d, rec, onMic }) {
  const { a, b, say } = d.pair;
  const target = say === "a" ? a : b;
  const tile = (x, key) => (
    <div class={`pair ${key === say ? "is-say" : ""}`} aria-current={key === say ? "true" : undefined}>
      {key === say && <span class="pair-flag">Say this</span>}
      <span class="pair-word">{x.word}</span>
      <span class="pair-ipa ipa">/{x.ipa.map((p, i) => <span class={(x.diff || []).includes(i) ? "diff" : ""}>{p}</span>)}/</span>
    </div>
  );
  return (
    <Shell title={d.title || "2-minute warm-up"}
      right={<span class="meta tabular" aria-label={`${fmtClock(d.seconds_left)} left, step ${d.step} of ${d.total}`}>{fmtClock(d.seconds_left)} · {d.step}/{d.total}</span>}>
      <div class="bar" aria-hidden="true"><span style={{ width: `${(1 - d.seconds_left / d.seconds_total) * 100}%` }} /></div>
      <p class="focus-label">{d.focus_label}</p>
      <div class="pairs">{tile(a, "a")}<span class="vs" aria-hidden="true">vs</span>{tile(b, "b")}</div>
      <footer class="actions">
        {d.last_attempt && (
          <p class="last"><StatusMark type={d.last_attempt.ok ? "ok" : "deletion"} size={16} /> {d.last_attempt.word} · {d.last_attempt.note}</p>
        )}
        <span class="spacer" />
        <MicButton rec={rec} onClick={onMic} label={`Say “${target.word}”`} />
      </footer>
    </Shell>
  );
}

/* ------------------------------------------------------------------ Listen (record in the card) */
export function MicButton({ rec, onClick, label, big }) {
  const on = rec?.state === "recording";
  return (
    <div class={`mic ${big ? "mic-big" : ""} ${on ? "is-on" : ""}`}>
      <button type="button" class="mic-btn" onClick={onClick} aria-label={on ? "Stop recording" : label} aria-pressed={on}>
        <Icon name={on ? "stop" : "mic"} size={big ? 32 : 24} />
      </button>
      <span class="mic-label">{on ? "Listening…" : rec?.state === "busy" ? "Checking every sound…" : label}</span>
      {on && <span class="levels" aria-hidden="true">{[0, 1, 2, 3, 4].map((i) => <i style={{ transform: `scaleY(${0.2 + Math.max(0, (rec.level || 0) - i * 0.12) * 1.2})` }} />)}</span>}
    </div>
  );
}

export function ListenCard({ d, rec, onMic, onRetry }) {
  const blocked = rec?.state === "unavailable" || d.mic_state;
  const reason = rec?.reason || d.mic_state;
  return (
    <Shell title="Say this sentence">
      <p class="target-sentence">{d.reference_text}</p>
      {blocked ? (
        <div class="fallback" role="status">
          <Icon name="info" size={24} />
          <div>
            <p class="fallback-title">{reason === "blocked" ? "The microphone is turned off for SpeakLoop on this screen." : "This screen can't share its microphone with SpeakLoop."}</p>
            <p class="fallback-body">Say it to Alexa instead. I'll check your words now, and every sound once the mic is on.</p>
          </div>
          <span class="spacer" />
          <Button onClick={onRetry} icon="mic">Try again</Button>
        </div>
      ) : (
        <footer class="actions listen-actions">
          <MicButton big rec={rec} onClick={onMic} label="Tap to record" />
          <p class="hint">{d.hint || "Tap the mic, or just say it to Alexa."}</p>
        </footer>
      )}
    </Shell>
  );
}

/* ------------------------------------------------------------------ Existing tool results, restyled */
export function PlanCard({ d, onStart }) {
  return (
    <Shell title={`Today · ${d.minutes} minutes`}>
      <h2 class="headline">{d.focus_label ? `Focus: ${d.focus_label}` : "Balanced practice"}</h2>
      <ol class="list">
        {(d.steps || []).slice(0, 4).map((s, i) => (
          <li class="list-row">
            <span class="list-n tabular">{i + 1}</span>
            <span class="list-main"><b>{s.label}</b><span class="list-sub">{s.why}</span></span>
            <span class="list-end tabular">{s.minutes} min</span>
          </li>
        ))}
      </ol>
      <footer class="actions"><span class="spacer" /><Button kind="primary" onClick={onStart}>Start step 1</Button></footer>
    </Shell>
  );
}

export function ResultCard({ d, onNext, onProgress }) {
  const s = d.score || {};
  const issues = new Map((s.issues || []).map((i) => [i.expected, i]));
  const tip = (d.tips || [])[0];
  const ref = d.reference || d.transcript || "";
  return (
    <Shell title={d.task_label || "Result"}>
      <h2 class="headline">{tip ? `Main fix: ${tip.label.toLowerCase()}` : s.correct === false ? `The answer is “${d.reference}”` : "Clear and steady."}</h2>
      {d.task_type !== "describe_image" && d.task_type !== "answer_short_question" && (
        <p class="diff">
          {ref.split(/\s+/).map((raw) => {
            const w = raw.toLowerCase().replace(/[^a-z0-9']/g, "");
            const iss = issues.get(w);
            if (!iss) return <span class="w-ok">{raw} </span>;
            const t = iss.heard && iss.feature ? "substitution" : "deletion";
            return <span class={`w-err w-${t}`}>{raw}<sup><StatusMark type={t} size={14} /></sup> </span>;
          })}
        </p>
      )}
      {tip && <p class="tip">{tip.en}</p>}
      {tip?.vi && <p class="gloss" lang="vi">{tip.vi}</p>}
      <footer class="actions">
        <span class="meta">{s.overall != null ? `Practice estimate ${s.overall}` : ""}</span>
        <span class="spacer" />
        <Button onClick={onProgress}>My progress</Button>
        <Button kind="primary" onClick={onNext}>Next drill</Button>
      </footer>
    </Shell>
  );
}

export function ProgressCard({ d }) {
  const p = d.profile || {};
  const series = d.daily || [];
  const W = 440, H = 150, pad = 8;
  const vals = series.map((x) => x.average);
  const lo = Math.min(...vals, p.target_score ?? Infinity) - 5, hi = Math.max(...vals, p.target_score ?? -Infinity) + 5;
  const x = (i) => pad + (series.length < 2 ? (W - 2 * pad) / 2 : (i * (W - 2 * pad)) / (series.length - 1));
  const y = (v) => H - pad - ((v - lo) / (hi - lo || 1)) * (H - 2 * pad);
  return (
    <Shell title="Progress" right={<span class="meta">{plural(p.streak_days || 0, "day", "days")} streak</span>}>
      <div class="progress">
        <div class="big-number"><span class="tabular">{p.estimated_score ?? "–"}</span><small>practice estimate{p.target_score ? ` · target ${p.target_score}` : ""}</small></div>
        {series.length > 0 ? (
          <svg class="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Practice estimate by day">
            {p.target_score && <line class="chart-target" x1="0" x2={W} y1={y(p.target_score)} y2={y(p.target_score)} />}
            <polyline class="chart-line" points={series.map((s, i) => `${x(i)},${y(s.average)}`).join(" ")} />
            {series.map((s, i) => <circle class="chart-dot" cx={x(i)} cy={y(s.average)} r="4" />)}
          </svg>
        ) : <p class="hint">No practice in this window yet.</p>}
      </div>
      <footer class="actions">
        <p class="next">{(p.weak_features || [])[0] ? <>Keep working on <b>{p.weak_features[0].label.toLowerCase()}</b></> : "No weak sounds recorded yet."}</p>
      </footer>
    </Shell>
  );
}

export function ReviewCard({ d }) {
  if (!d.drill_id) return <Shell title="Sound review"><h2 class="headline">{d.message || "Nothing to review today."}</h2></Shell>;
  return (
    <Shell title="Sound review" right={<span class="meta">{plural((d.items || []).length, "word", "words")}</span>}>
      <h2 class="headline">{d.prompt || "Say each word clearly."}</h2>
      <ol class="list">
        {(d.items || []).slice(0, 4).map((i, n) => (
          <li class="list-row"><span class="list-n tabular">{n + 1}</span><span class="list-main"><b>{i.word}</b><span class="list-sub">{i.tip || i.feature}</span></span><span class="list-end">missed {i.lapses}×</span></li>
        ))}
      </ol>
    </Shell>
  );
}

export function RoutineCard({ d, onCalendar }) {
  return (
    <Shell title="Daily routine">
      <div class="big-number"><span class="tabular">{d.time_local}</span><small>{d.days?.split(",").length === 7 ? "every day" : (d.days || "").replace(/,/g, " · ")} · {d.minutes} minutes</small></div>
      <footer class="actions"><span class="spacer" /><Button kind="primary" icon="calendar" onClick={onCalendar}>Add to calendar</Button></footer>
    </Shell>
  );
}

export function SimpleCard({ title, head, body, vi }) {
  return (
    <Shell title={title}>
      <h2 class="headline">{head}</h2>
      {body && <p class="tip">{body}</p>}
      {vi && <p class="gloss" lang="vi">{vi}</p>}
    </Shell>
  );
}

export function DrillLegacyCard({ d }) {
  return (
    <Shell title={d.task_label} right={d.time_limit_seconds ? <span class="meta tabular">{d.time_limit_seconds}s</span> : null}>
      <h2 class="headline">{d.prompt}</h2>
      {d.display_text ? <p class="passage">{d.display_text}</p> : <p class="passage muted"><Icon name="speaker" size={24} /> Listen, then say it back.</p>}
    </Shell>
  );
}

export { Brand };
