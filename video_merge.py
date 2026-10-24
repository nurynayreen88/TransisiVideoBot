"""CPU-friendly FFmpeg video merge for short affiliate clips."""
import subprocess
import tempfile
from pathlib import Path

ALLOWED = {"none", "fade", "smoothleft", "slideleft", "zoomin"}

def run(args, timeout=180):
    subprocess.run(args, check=True, timeout=timeout, capture_output=True)

def duration(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True, timeout=20)
    return float(p.stdout.strip())

def has_audio(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True, timeout=20)
    return bool(result.stdout.strip())

def merge_videos(sources, destination, transition="none"):
    if transition not in ALLOWED or not 2 <= len(sources) <= 5:
        raise ValueError("Invalid merge request")
    with tempfile.TemporaryDirectory(prefix="merge_clips_") as folder:
        clips, durations = [], []
        for index, src in enumerate(sources):
            seconds = duration(src)
            if not 1.0 <= seconds <= 20.0:
                raise ValueError("Each clip must be 1-20 seconds")
            clip = Path(folder) / f"clip_{index}.mp4"
            cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
            if not has_audio(src):
                cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
            cmd += ["-map", "0:v:0", "-map", "0:a:0" if has_audio(src) else "1:a:0",
                    "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,"
                           "pad=720:1280:(ow-iw)/2:(oh-ih)/2:black,"
                           "setsar=1,fps=30,format=yuv420p",
                    "-af", "aresample=44100,apad",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
                    "-t", str(seconds), str(clip)]
            run(cmd)
            clips.append(clip)
            durations.append(duration(clip))
        if transition == "none":
            # All clips were normalized to matching video and audio streams.
            listing = Path(folder) / "concat.txt"
            listing.write_text(
                "".join(f"file '{clip.as_posix()}'\n" for clip in clips),
                encoding="utf-8",
            )
            run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                 "-i", str(listing), "-map", "0:v:0", "-map", "0:a:0",
                 "-c", "copy", "-movflags", "+faststart", str(destination)], timeout=240)
            return
        args = ["ffmpeg", "-y", "-v", "error"]
        for clip in clips:
            args.extend(["-i", str(clip)])
        overlap = 0.35
        total = durations[0]
        prev = "[0:v]"
        previous_audio = "[0:a]"
        filters = []
        for index in range(1, len(clips)):
            label = f"[m{index}]"
            offset = max(0, total - overlap)
            filters.append(
                f"{prev}[{index}:v]xfade=transition={transition}:"
                f"duration={overlap}:offset={offset:.3f}{label}")
            audio_label = f"[a{index}]"
            filters.append(
                f"{previous_audio}[{index}:a]acrossfade=d={overlap}:c1=tri:c2=tri{audio_label}")
            previous_audio = audio_label
            total += durations[index] - overlap
            prev = label
        args += ["-filter_complex", ";".join(filters), "-map", prev, "-map", previous_audio,
                 "-c:a", "aac", "-b:a", "160k", "-c:v", "libx264", "-preset", "veryfast",
                 "-crf", "18", "-pix_fmt", "yuv420p",
                 "-movflags", "+faststart", str(destination)]
        run(args, timeout=240)
