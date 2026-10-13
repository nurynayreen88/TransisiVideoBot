FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py generate_music.py video_merge.py fusion_animation.py ./
COPY fusion_assets/ ./fusion_assets/
COPY klippo_qr.jpg ./klippo_qr.jpg
RUN python generate_music.py
CMD ["python", "bot.py"]
