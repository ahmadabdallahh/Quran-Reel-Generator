# Hugging Face Spaces — Docker SDK
# Quran Reels Generator | Flask + FFmpeg
# HF expects the web server on 7860 and host 0.0.0.0.

FROM python:3.11-slim

# ---- System deps: FFmpeg (+ ffprobe) + tini for signal handling ----
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -version | head -n1 && ffprobe -version | head -n1

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ---- Python deps (layer-cached) ----
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ---- App code ----
# Keep build context lean via .dockerignore; vision/ (background mp4s) is intentionally included.
COPY . .

# Ensure runtime dirs exist (cache/outputs are gitignored but needed at runtime)
RUN mkdir -p cache/audio cache/backgrounds outputs/video temp \
    && chmod -R 755 cache outputs temp

# HF Spaces variables — app reads QURAN_* but we also honour $PORT if set
ENV QURAN_FLASK_HOST=0.0.0.0 \
    QURAN_FLASK_PORT=7860 \
    QURAN_FLASK_DEBUG=false \
    PORT=7860

EXPOSE 7860

# Use tini as init to handle SIGTERM correctly on Spaces
ENTRYPOINT ["tini", "--"]
CMD ["python", "main.py"]
