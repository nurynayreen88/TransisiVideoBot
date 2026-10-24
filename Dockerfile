FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY affiliate_image_tools.py bot.py generate_music.py video_merge.py fusion_animation.py klippo_db.py storyboard_engine.py storyboard_overlay.py gemini_vision.py gemini_storyboard.py gemini_storyboard_image.py prompt_engine.py prompt_catalog.py prompt_model_defaults.py prompt_copy.py caption_hashtags.py ./
COPY fal_storyboard_test.py ./fal_storyboard_test.py
COPY modules/ ./modules/
COPY prompts/ ./prompts/
COPY fusion_assets/ ./fusion_assets/
COPY klippo_qr.jpg ./klippo_qr.jpg
RUN python generate_music.py
CMD ["python", "bot.py"]
