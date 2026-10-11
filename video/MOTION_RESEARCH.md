# What makes a launch film feel premium — 10 rules for the SpeakLoop remake

Sources read (2026-10-11):
- Remocn, "Making a launch video for Claude Opus 5" — https://remocn.dev/blog/claude-opus-5-launch-video
- Impractical, "Introducing Linear Agent — a motion breakdown" — https://impractical.ai/launch-videos/linear-agent
- Supaintro, "Launch video examples, read properly" — https://supaintro.com/guides/launch-video-examples
- Search excerpts (not opened in full): Impractical breakdowns of Raycast "It's out" and Claude Code; Frame24 on Linear and Vercel ship videos.

## The rules

1. **Name the product inside 5 seconds; spend cleverness after.** Hook (the problem in one picture) → name → promise.
   Judges decide in the first 30 s, so the hook, the name and the core proof must all land before 0:30. (Supaintro)
2. **One idea per scene, one claim per frame.** Pause anywhere: exactly one line of copy is on screen. (Supaintro, Raycast)
3. **Type is the narrator.** One typeface (Atkinson Hyperlegible Next), one or two weights, set huge, sentence case,
   no letter-spaced uppercase eyebrows, no badges. It must survive muted playback. (Frame24/Linear, Remocn)
4. **One accent, spent only on the payoff.** #FF8A3D appears on the payoff word, the winning bar, the flagged phoneme —
   nowhere decorative. Everything else is ink-on-dark. (Remocn: clay used only on payoff word / winning bar / spark)
5. **Masked reveals, not fades.** Lines slide up from behind an invisible edge with sharp edges; no blur-in, no bounce,
   no "pulsing". (Linear Agent breakdown)
6. **Easing: fast attack, long settle.** easeOutExpo / critically-damped springs on transform; opacity on a short
   separate ramp (≈1/3 the length). Two properties of one element never share one curve. (Remocn, Linear)
7. **Compressed stagger + follow-through.** Stagger = base × i^0.8; children (a check, a ratio) land a few frames after
   their parent. Cascades mirror the product's own UI rhythm. (Remocn, Linear)
8. **Cuts on the beat, holds where reading happens.** Scene changes land on the bar of the music; numbers and UI are
   held long enough to read twice. Never cut before text can be read. (Supaintro, Claude Code, Vercel)
9. **The interface is the evidence — and the camera is directed.** Use the real product screens, push in hard on the
   one element that matters (punch-ins), slow engineered drift otherwise; perspective tilt for the reveal shot only.
   No stock footage, no glowing orbs, no presenters. (Raycast, Linear, Claude Code)
10. **One continuous canvas; boring end card.** A persistent background/vignette so cuts read as camera moves, no blank
   frames between scenes (pre-roll each scene's first element). End on name + URL held still for 3+ s. (Remocn, Supaintro)

## Applied to SpeakLoop
- Minimal/no narration; captions do the talking; music carries the rhythm (bpm grid drives scene boundaries).
- Real numbers only, labeled with dataset: L2-ARCTIC, Vietnamese L1, same 100 held-out utterances:
  recall 0.53 vs 0.22, F1 0.56 vs 0.32 (benchmarks/RESULTS.md on feat/phoneme).
- No "trusted by", no user counts, no unverifiable claims.
