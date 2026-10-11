# SpeakLoop launch film (Remotion)

A 2:18 motion-design launch film for SpeakLoop (1920×1080, 30 fps) plus a 32 s vertical teaser (1080×1920).
v2: the product scenes render the real card components (feat/ui) at real speed, the new /d/ mark (feat/brand),
and a Kokoro-82M voice (Apache-2.0) instead of the earlier synthetic learner voice.
Built with [Remotion](https://remotion.dev) 4 — every frame is React, every number on screen comes from the repo.

```bash
cd video
npm install
python3 scripts/make_music.py                                   # public/music.wav (synthesised score, 120 BPM)
python3 scripts/make_music.py src/music_teaser.json music_teaser.wav
python3 scripts/vendor_ui.py ../path/to/speakloop-on-feat-ui                   # src/ui/ (only when the card changes)
python3 scripts/mix_audio.py launch && python3 scripts/mix_audio.py teaser     # voice (src/vo.json) over ducked music
scripts/render_chunks.sh Launch out/chunks 300 4140                             # resumable chunked render
npx remotion studio                                             # preview
npx remotion render Launch out/speakloop_launch.mp4 --concurrency=1
npx remotion render Teaser out/speakloop_teaser_vertical.mp4 --concurrency=1
node scripts/stills.mjs Launch out/stills 150 940 2720          # review frames
```

- `src/Root.tsx` — timeline. Every scene boundary is a multiple of 60 frames = one bar at 120 BPM, so cuts land on downbeats.
- `src/lib.tsx` — design tokens (from `ui/src/tokens.css`), masked text reveals, easing, stage (vignette + grain), 3D frame.
- `src/scenesA.tsx`, `src/scenesB.tsx`, `src/sceneReal.tsx` — the twelve scenes; `src/UICard.tsx` renders the vendored card (`src/ui/`).
- `src/vo.json` — when each voice line plays; `public/vo/` — the Kokoro lines (regenerate: see CREDITS.md).
- `MOTION_RESEARCH.md` — the ten rules the film follows. `CREDITS.md` — licences (music is original, synthesised).

Licences of bundled assets: see `CREDITS.md`. Remotion is free for individuals and small teams; check
https://remotion.dev/license for company use.
