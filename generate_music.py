"""Generate six royalty-free synthetic instrumentals at image build time; no API or extra pip deps."""
import math
import subprocess
import wave
from pathlib import Path

OUT = Path(__file__).resolve().parent / "music"
OUT.mkdir(exist_ok=True)
RATE = 22050
DURATION = 16
TRACKS = {
    "luxury": ([220, 277.18, 329.63, 440], 72, "soft"),
    "beauty": ([261.63, 329.63, 392, 523.25], 90, "soft"),
    "energetic": ([220, 329.63, 440, 554.37], 124, "beat"),
    "cinematic": ([174.61, 261.63, 349.23, 440], 80, "dramatic"),
    "nature": ([196, 246.94, 293.66, 392], 84, "soft"),
    "happy": ([261.63, 329.63, 392, 493.88], 112, "beat"),
}
for name, (notes, bpm, mood) in TRACKS.items():
    samples = [0.0] * (RATE * DURATION)
    beat = 60.0 / bpm
    for j in range(int(DURATION / beat) + 1):
        start = int(j * beat * RATE)
        end = min(len(samples), start + int(beat * 1.8 * RATE))
        if start >= end:
            continue
        freq = notes[j % len(notes)] / (2 if mood == "dramatic" else 1)
        for k in range(start, end):
            q = (k - start) / RATE
            env = min(1, q / .035) * math.exp(-q / (beat * (1.5 if mood == "soft" else .75)))
            tone = math.sin(2 * math.pi * freq * q) + .22 * math.sin(4 * math.pi * freq * q) + .09 * math.sin(6 * math.pi * freq * q)
            samples[k] += tone * env * .13
            if mood == "beat" and q < .14:
                samples[k] += .16 * math.sin(2 * math.pi * (100 - 55 * q / .14) * q) * math.exp(-q * 35)
    import array
    pcm = array.array("h", (int(max(-.9, min(.9, v * min(1, i / (RATE * .5)) * min(1, (len(samples)-i)/(RATE*1.5)))) * 32767) for i, v in enumerate(samples)))
    wav = OUT / (name + ".wav")
    with wave.open(str(wav), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(RATE)
        file.writeframes(pcm.tobytes())
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "96k", str(OUT / (name + ".mp3"))], check=True)
    wav.unlink()
    print("Created", name)
