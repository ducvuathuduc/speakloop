#!/bin/bash
# Chunked, resumable render for a shared machine that restarts: each chunk is its own file and is
# skipped when it already exists. usage: scripts/render_chunks.sh <Comp> <outdir> <chunkFrames> <totalFrames>
comp=$1; dir=$2; step=$3; total=$4
mkdir -p "$dir"
for ((a=0; a<total; a+=step)); do
  b=$((a+step-1)); [ $b -ge $total ] && b=$((total-1))
  f=$(printf "%s/%05d-%05d.mp4" "$dir" $a $b)
  [ -s "$f" ] && continue
  npx remotion render $comp "$f.part.mp4" --frames=$a-$b --concurrency=1 --log=error && mv "$f.part.mp4" "$f"
done
echo ALLDONE
