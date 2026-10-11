# TransisiVideoBot — Render Free experiment

Telegram webhook bot; Python + FFmpeg, no paid video API. Render Free has limited CPU/RAM, can spin down and has ephemeral disk. Not guaranteed for long video rendering. Try 1–3 photos initially.

## Render deployment
1. Upload `bot.py`, `requirements.txt`, `Dockerfile` to a separate private GitHub repo (keep the GitHub README/.gitignore if already present).
2. Render → New → Web Service → Connect repository → Runtime: Docker → Instance: Free (if available).
3. Set environment variables:
   - BOT_TOKEN: token from BotFather (secret; never commit)
   - WEBHOOK_URL: `https://YOUR-SERVICE.onrender.com` (actual Render service URL, no trailing slash)
   - WEBHOOK_SECRET: random letters/numbers/underscore/hyphen, 32+ chars (secret)
   - MAX_IMAGES: 5
   - VIDEO_SECONDS: 10
4. Deploy. Once live, send /start, 2 photos, /jana.
5. If a render fails due to memory or timeout, use local Windows hosting or paid CPU service. The bot cannot guarantee 24/7 operation on Render Free.

No persistent database. Photos are kept as Telegram file IDs in memory and will reset on service restart. Temporary downloaded images and rendered videos are deleted after each job. Avoid sensitive office images.
