# ── Reel Engine Production Dockerfile ──────────────────────────
FROM python:3.11-slim

# Install system dependencies (FFmpeg for video compilation, espeak-ng for local voiceover)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    espeak-ng \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir APScheduler>=3.10.0

# Copy Reel Engine codebase
COPY . /app/reel_engine

# Set Python module search path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Run master production daemon by default
CMD ["python", "-m", "reel_engine.main", "daemon"]
