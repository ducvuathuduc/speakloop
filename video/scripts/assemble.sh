#!/bin/bash
# Join chunk renders (video only, stream copy) and mux the full mixed soundtrack.
# usage: scripts/assemble.sh <chunkdir> <mix.wav> <out.mp4>
set -e
dir=$1; mix=$2; out=$3
ls "$dir"/[0-9]*-[0-9]*.mp4 | sort | sed "s|^|file '$PWD/|; s|$|'|" > "$dir/list.txt"
ffmpeg -v error -y -f concat -safe 0 -i "$dir/list.txt" -an -c:v copy "$dir/video.mp4"
ffmpeg -v error -y -i "$dir/video.mp4" -i "$mix" -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart "$out"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$out"
