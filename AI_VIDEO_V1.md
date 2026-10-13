# Klippo Video AI V1 — worker contract (staging)

Goal: one uploaded image -> one 10-second MP4. Users never handle intermediate clips.

1. GPU worker accepts a reference image and a constrained motion prompt.
2. Generate clip A of at least 5.5 seconds.
3. Extract the last frame of A and use it with the original reference image to guide clip B, also at least 5.5 seconds. Preserve product identity. The worker must actually generate both clips; do not substitute FFmpeg zoom for AI generation.
4. Download both completed MP4s to an isolated temporary directory on the bot worker.
5. Call `assemble_ai_10s(clip_a, clip_b, final_mp4)`. It validates source durations, normalizes portrait video and crossfades into an exact 10-second output.
6. Send only the final MP4. Clean temporary files. On failure, report failure; never charge an AI quota for an uncompleted video.

**Not connected yet:** GPU execution/provider, job queue, persistent per-user daily quota, cancellation/retry and real-generation tests. Keep Video AI (Limited) disabled until those are implemented and validated. Render Free is only the Telegram/orchestration service, not a GPU worker.
