#!/bin/bash
# Splice re-rendered chunks into an earlier full render (used when the shared sandbox killed a full render).
# usage: scripts/splice.sh base.mp4 a.mp4(480-1139) b.mp4(2400-2879) out.mp4
set -e
ffmpeg -v error -y -i "$1" -i "$2" -i "$3" -filter_complex "\
[0:v]split=3[s0][s1][s2];\
[s0]trim=start_frame=0:end_frame=480,setpts=PTS-STARTPTS[v0];\
[1:v]setpts=PTS-STARTPTS[v1];\
[s1]trim=start_frame=1140:end_frame=2400,setpts=PTS-STARTPTS[v2];\
[2:v]setpts=PTS-STARTPTS[v3];\
[s2]trim=start_frame=2880:end_frame=3900,setpts=PTS-STARTPTS[v4];\
[v0][v1][v2][v3][v4]concat=n=5:v=1:a=0,fps=30[v]" \
  -map "[v]" -map 0:a -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -threads 2 -c:a copy -movflags +faststart "$4"
