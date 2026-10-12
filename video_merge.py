"""CPU-friendly FFmpeg video merge for short affiliate clips."""
import subprocess
import tempfile
from pathlib import Path

ALLOWED = {"fade", "smoothleft", "slideleft", "zoomin"}

def run(args, timeout=180):
    subprocess.run(args, check=True, timeout=timeout, capture_output=True)

def duration(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True, timeout=20)
    return float(p.stdout.strip())

def merge_videos(sources, destination, transition="fade"):
    if transition not in ALLOWED or not 2 <= len(sources) <= 5:
        raise ValueError("Invalid merge request")
    with tempfile.TemporaryDirectory(prefix="merge_clips_") as folder:
        clips, durations = [], []
        for index, src in enumerate(sources):
            seconds = duration(src)
            if not 1.0 <= seconds <= 20.0:
                raise ValueError("Each clip must be 1-20 seconds")
            clip = Path(folder) / f"clip_{index}.mp4"
            run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                 "-map", "0:v:0",
                 "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,"
                        "pad=720:1280:(ow-iw)/2:(oh-ih)/2:black,"
                        "setsar=1,fps=30,format=yuv420p",
                 "-an", "-c:v", "libx264", "-preset", "veryfast",
                 "-crf", "20", "-t", str(seconds), str(clip)])
            clips.append(clip)
            durations.append(duration(clip))
        args = ["ffmpeg", "-y", "-v", "error"]
        for clip in clips:
            args.extend(["-i", str(clip)])
        overlap = 0.35
        total = durations[0]
        prev = "[0:v]"
        filters = []
        for index in range(1, len(clips)):
            label = f"[m{index}]"
            offset = max(0, total - overlap)
            filters.append(
                f"{prev}[{index}:v]xfade=transition={transition}:"
                f"duration={overlap}:offset={offset:.3f}{label}")
            total += durations[index] - overlap
            prev = label
        args += ["-filter_complex", ";".join(filters), "-map", prev,
                 "-an", "-c:v", "libx264", "-preset", "veryfast",
                 "-crf", "18", "-pix_fmt", "yuv420p",
                 "-movflags", "+faststart", str(destination)]
        run(args, timeout=240)
