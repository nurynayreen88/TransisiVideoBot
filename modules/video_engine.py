"""Low-cost local vertical video assembly using FFmpeg + gTTS."""
from pathlib import Path
import logging
import shutil
import subprocess
import tempfile

from gtts import gTTS
from PIL import Image, ImageOps

WIDTH, HEIGHT = 720, 1280
MIN_TOTAL_SECONDS = 3.6
FPS = 30


def calculate_panel_durations(audio_duration: float, minimum_total: float = MIN_TOTAL_SECONDS) -> tuple[float, float]:
    """Return equal panel durations long enough for the full narration plus a small tail."""
    if audio_duration <= 0:
        raise ValueError("Audio duration must be positive.")
    total = max(minimum_total, audio_duration + 0.25)
    each = total / 2
    return each, each


def _mutagen_duration(path: Path) -> float | None:
    """Read MP3 duration with Mutagen when ffprobe is unavailable or fails."""
    try:
        from mutagen.mp3 import MP3
        duration = float(MP3(str(path)).info.length)
        return duration if duration > 0 else None
    except Exception as exc:
        logging.warning("Mutagen could not read audio duration: %s", type(exc).__name__)
        return None


def _probe_duration(path: Path, fallback_text: str = "") -> float:
    """Measure audio duration; fall back to Mutagen, then a speech estimate."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                duration = float(result.stdout.strip())
                if duration > 0:
                    return duration
            logging.warning("ffprobe could not determine audio duration; trying Mutagen.")
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            logging.warning("ffprobe failed (%s); trying Mutagen.", type(exc).__name__)

    duration = _mutagen_duration(path)
    if duration is not None:
        return duration

    word_count = len(fallback_text.split())
    if word_count:
        estimate = max(0.8, word_count / 2.6)
        logging.warning(
            "Audio duration estimated from %s narration words (%.2fs); install FFmpeg/ffprobe for best timing.",
            word_count, estimate,
        )
        return estimate
    raise RuntimeError("Could not determine audio duration; provide narration text or install FFmpeg/ffprobe.")


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-1200:]}")


def create_video(panel_paths: list[str | Path], narration_ms: str, output_path: str | Path) -> Path:
    """Create an MP4 from exactly two panel images and Malaysian Malay narration."""
    if len(panel_paths) != 2:
        raise ValueError("Beta video engine expects exactly two storyboard panels.")
    if not narration_ms.strip():
        raise ValueError("Voiceover text must not be empty.")
    if len(narration_ms) > 500:
        raise ValueError("Voiceover exceeds the 500-character gTTS limit. Shorten the sentence; it will not be silently truncated.")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is not installed.")
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="klippo-video-") as tmp:
        work = Path(tmp)
        normalized = []
        for index, source in enumerate(panel_paths, start=1):
            source = Path(source)
            if not source.is_file():
                raise FileNotFoundError(f"Panel image not found: {source}")
            with Image.open(source) as image:
                frame = ImageOps.fit(image.convert("RGB"), (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
                frame_path = work / f"panel_{index}.jpg"
                frame.save(frame_path, quality=94)
                normalized.append(frame_path)

        audio_path = work / "voiceover.mp3"
        gTTS(text=narration_ms, lang="ms", slow=False).save(str(audio_path))
        audio_duration = _probe_duration(audio_path, narration_ms)
        panel_durations = calculate_panel_durations(audio_duration)
        clips = []
        for index, (frame_path, panel_seconds) in enumerate(zip(normalized, panel_durations), start=1):
            clip_path = work / f"clip_{index}.mp4"
            vf = (
                f"zoompan=z='min(zoom+0.00075,1.04)':d={max(1, int(round(panel_seconds*FPS)))}:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={WIDTH}x{HEIGHT}:fps={FPS},format=yuv420p"
            )
            _run([ffmpeg, "-y", "-loop", "1", "-i", str(frame_path), "-vf", vf,
                  "-t", f"{panel_seconds:.3f}", "-r", str(FPS), "-an",
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", str(clip_path)])
            clips.append(clip_path)

        concat_file = work / "concat.txt"
        concat_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips), encoding="utf-8")
        silent_video = work / "silent.mp4"
        _run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
              "-c", "copy", str(silent_video)])
        total_duration = sum(panel_durations)
        staged_output = work / "video_output.mp4"
        _run([ffmpeg, "-y", "-i", str(silent_video), "-i", str(audio_path),
              "-map", "0:v:0", "-map", "1:a:0", "-t", f"{total_duration:.3f}",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
              str(staged_output)])
        # Publish only a fully rendered MP4; intermediate files stay inside TemporaryDirectory.
        shutil.move(str(staged_output), str(output))
    return output
