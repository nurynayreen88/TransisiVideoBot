# Klippo fal.ai Storyboard Beta (isolated)

This is an experimental test bot and must run as a **separate Render service** with its own Telegram bot token. Do not change the existing live Klippo service or reuse its Telegram bot token.

## 1. Create a separate Telegram test bot
1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Run `/newbot` and follow the steps.
3. Copy the new test bot token. Do not share it in chat or commit it to GitHub.

## 2. Create a separate Render service
1. In Render, choose **New + → Web Service** (or the service type your account uses for a continuously running worker).
2. Connect `nurynayreen88/TransisiVideoBot`.
3. Select branch `test/fal-storyboard-beta`.
4. Use the existing Dockerfile.
5. Set the Start Command to `python fal_storyboard_test_bot.py`.
6. Add Environment Variables:
   - `FAL_TEST_BOT_TOKEN` = token from the separate Telegram test bot
   - `FAL_KEY` = fal.ai API key
   - `GEMINI_API_KEY` = optional, only if you want Gemini to analyse the reference image
7. Keep the existing production Klippo service unchanged. Do not attach the production bot token to this test service.

## 3. Run a test
Open the new Telegram test bot, send `/start`, then send one product photo. It attempts to generate two panels using `fal-ai/flux-kontext/dev` and returns a two-panel contact sheet.

## Notes
- API calls may incur charges. Check fal.ai pricing and usage before testing.
- This is an experiment, not a guarantee that product labels or logos will be reproduced perfectly.
- The test bot is independent of the live Klippo bot; do not merge this branch into the production branch until the output has been reviewed.
