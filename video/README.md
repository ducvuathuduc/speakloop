# SpeakLoop launch film (Remotion)

A ~2:10 motion-design launch film for SpeakLoop (1920×1080, 30 fps) plus a 30 s vertical teaser (1080×1920).
Built with [Remotion](https://remotion.dev) 4 — every frame is React, every number on screen comes from the repo.

```bash
cd video
npm install
python3 scripts/make_music.py                                   # public/music.wav (synthesised score, 120 BPM)
python3 scripts/make_music.py src/music_teaser.json music_teaser.wav
npx remotion studio                                             # preview
npx remotion render Launch out/speakloop_launch.mp4 --concurrency=1
npx remotion render Teaser out/speakloop_teaser_vertical.mp4 --concurrency=1
node scripts/stills.mjs Launch out/stills 150 940 2720          # review frames
```

- `src/Root.tsx` — timeline. Every scene boundary is a multiple of 60 frames = one bar at 120 BPM, so cuts land on downbeats.
- `src/lib.tsx` — design tokens (from `ui/src/tokens.css`), masked text reveals, easing, stage (vignette + grain), 3D frame.
- `src/scenesA.tsx`, `src/scenesB.tsx` — the twelve scenes.
- `MOTION_RESEARCH.md` — the ten rules the film follows. `CREDITS.md` — licences (music is original, synthesised).

Licences of bundled assets: see `CREDITS.md`. Remotion is free for individuals and small teams; check
https://remotion.dev/license for company use.
