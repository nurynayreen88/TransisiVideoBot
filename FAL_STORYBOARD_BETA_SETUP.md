# Klippo Storyboard + Video Beta (isolated test branch)

This is experimental. Run as a separate Render service with a separate Telegram bot token. Do not alter the production service, production token, or main branch.

## Required environment variables
- `FAL_TEST_BOT_TOKEN`: token for the separate Telegram test bot
- `FAL_KEY`: fal.ai API key
- `GEMINI_API_KEY`: Gemini key for JSON visual attributes and a short Malay voiceover line
- Optional `GEMINI_VISION_MODEL` (default `gemini-2.5-flash`)
- Optional `FAL_STORYBOARD_MODEL` (default `fal-ai/flux-kontext/dev`)

Never commit keys or paste them into chat.

## Isolated Render service
1. Create a separate Render service using repository `nurynayreen88/TransisiVideoBot`.
2. Select branch `test/fal-storyboard-beta`.
3. Use the repository Dockerfile.
4. Set the start command to `python fal_storyboard_test_bot.py`.
5. Set the environment variables listed above.
6. Keep the live Klippo service unchanged. Do not reuse its Telegram bot token.

## Minimum live API test (local)
Install Python 3.11+, FFmpeg, and requirements:
```bash
pip install -r requirements.txt
```
Set `FAL_KEY` and `GEMINI_API_KEY` in your local environment without writing them into source files. Then run:
```bash
python fal_storyboard_test.py ./product.jpg --out ./fal_storyboard_test_output
```
PowerShell environment-variable example (enter keys locally; do not paste them into chat):
```powershell
$env:FAL_KEY = Read-Host "Enter fal.ai key locally"
$env:GEMINI_API_KEY = Read-Host "Enter Gemini key locally"
python .\fal_storyboard_test.py .\product.jpg --out .\fal_storyboard_test_output
```
The script generates exactly two panels and reports Gemini latency, upload latency, per-panel latency, total latency, and Gemini token usage when returned. fal.ai cost is not guessed from latency: record the fal.ai Usage/Billing dashboard before and after the run to determine actual credits/cost.

## Telegram UX
1. Send a product photo.
2. Choose `🛍️ Shopee Affiliate` or `🎵 TikTok Viral`.
3. Choose `🖼️ Storyboard Panel (Gambar)` or `🎬 Video Motion + Voiceover`.

The video path assembles two generated panels locally with FFmpeg, applies a subtle slow zoom, and uses gTTS Malay speech. gTTS needs internet access and is basic text-to-speech, not a custom AI voice. Target output is 1080x1920 MP4, 3.6 seconds total (two panels at 1.8 seconds each). Keep the Gemini narration short because audio longer than the 3.6-second video is cut off.

## Review checklist
- Compare original and both panels for silhouette, colour, material appearance, label/logo and accessories.
- Record actual fal.ai usage/cost from the dashboard.
- Check MP4 dimensions, duration, voice intelligibility and Telegram playback.
- AI image generation cannot guarantee perfect product/logo preservation.
- Do not merge to main or deploy production until explicitly approved.
