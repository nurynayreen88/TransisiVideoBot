"""Assemble two real AI-generated clips into a 10-second portrait video.

The GPU worker must generate the clips. This module never simulates AI motion.
Each source clip must be at least 5.5 seconds, preferably generated with
continuity (the last frame of clip 1 as reference for clip 2).
"""
from pathlib import Path
import json
import subprocess

WIDTH, HEIGHT, FPS = 480, 854, 24

class AssemblyError(RuntimeError):
    pass

def _run(args, timeout=180):
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise AssemblyError(str(exc)) from exc

def _duration(path):
    result = _run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                   '-of', 'json', str(path)], timeout=30)
    return float(json.loads(result.stdout)['format']['duration'])

def assemble_ai_10s(first: Path, second: Path, output: Path):
    """Join two >=5.5s clips using a 1s crossfade: 5.5 + 5.5 - 1 = 10s."""
    first, second, output = Path(first), Path(second), Path(output)
    if not first.is_file() or not second.is_file():
        raise AssemblyError('Both AI-generated clips are required')
    if first.resolve() == second.resolve() or output.resolve() in (first.resolve(), second.resolve()):
        raise AssemblyError('Input clips and output must be distinct')
    if _duration(first) < 5.5 or _duration(second) < 5.5:
        raise AssemblyError('Each AI clip must be at least 5.5 seconds')
    output.parent.mkdir(parents=True, exist_ok=True)
    filtergraph = (
        f'[0:v]trim=duration=5.5,setpts=PTS-STARTPTS,fps={FPS},'
        f'scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,'
        f'crop={WIDTH}:{HEIGHT},setsar=1,format=yuv420p[v0];'
        f'[1:v]trim=duration=5.5,setpts=PTS-STARTPTS,fps={FPS},'
        f'scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,'
        f'crop={WIDTH}:{HEIGHT},setsar=1,format=yuv420p[v1];'
        '[v0][v1]xfade=transition=fade:duration=1:offset=4.5,'
        'trim=duration=10,setpts=PTS-STARTPTS[out]'
    )
    _run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
          '-i', str(first), '-i', str(second),
          '-filter_complex', filtergraph, '-map', '[out]',
          '-an', '-r', str(FPS), '-c:v', 'libx264', '-preset', 'veryfast',
          '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-t', '10',
          str(output)], timeout=300)
    if not output.is_file() or output.stat().st_size == 0:
        raise AssemblyError('Output video was not created')
    if abs(_duration(output) - 10) > 0.15:
        raise AssemblyError('Output video duration is not 10 seconds')
    return output
