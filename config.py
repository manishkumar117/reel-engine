"""
config.py — Central configuration for Reel Engine.
Contains all system paths, CLI commands, audio/video parameters, cloud storage,
and email notification settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent.resolve()
RUNS_DIR      = BASE_DIR / "runs"
AUDIO_DIR     = BASE_DIR / "audio"
MUSIC_DIR     = AUDIO_DIR / "background_music"
SUBTITLES_DIR = BASE_DIR / "subtitles"
COMPILER_DIR  = BASE_DIR / "compiler"
NOTIFIER_DIR  = BASE_DIR / "notifier"
STORAGE_DIR   = BASE_DIR / "storage"
PUBLISHER_DIR = BASE_DIR / "publisher"

# Ensure runtime directories exist
RUNS_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

# ── Load Environment Variables (Cascading priority) ───────────────────────────
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR.parent / "trend_engine" / ".env")  # Inherit existing Gmail credentials

# ── CLI & Subprocess Binaries ──────────────────────────────────────────────────
AGY_CMD          = os.getenv("AGY_CMD", "agy")
AGY_TIMEOUT_SECS = int(os.getenv("AGY_TIMEOUT_SECS", "120"))
FFMPEG_CMD       = os.getenv("FFMPEG_CMD", "ffmpeg")

# ── Email Communication (Gmail SMTP / IMAP) ──────────────────────────────────
GMAIL_ADDRESS           = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD      = os.getenv("GMAIL_APP_PASSWORD", "")
ALERT_RECIPIENT         = os.getenv("ALERT_RECIPIENT", GMAIL_ADDRESS)
IMAP_POLL_INTERVAL_SECS = int(os.getenv("IMAP_POLL_INTERVAL_SECS", "60"))

# ── Google Drive Human-in-the-Loop Hub ────────────────────────────────────────
GDRIVE_SERVICE_ACCOUNT_FILE = os.getenv("GDRIVE_SERVICE_ACCOUNT_FILE", "service_account.json")
GDRIVE_MASTER_FOLDER_ID     = os.getenv("GDRIVE_MASTER_FOLDER_ID", "")

# ── Cloudflare R2 / AWS S3 Public Video Storage ───────────────────────────────
R2_ACCOUNT_ID      = os.getenv("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID   = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME     = os.getenv("R2_BUCKET_NAME", "")
PUBLIC_STORAGE_URL = os.getenv("PUBLIC_STORAGE_URL", "")

# ── Supabase Cloud Storage (Direct Public Video Endpoint & Asset Hub) ─────────
SUPABASE_URL         = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_BUCKET      = os.getenv("SUPABASE_BUCKET", "reel-engine")

# ── Video & Audio Specifications (Instagram Reels Standard) ───────────────────
TARGET_WIDTH       = 1080
TARGET_HEIGHT      = 1920
TARGET_FPS         = 30
VIDEO_CODEC        = "libx264"
AUDIO_CODEC        = "aac"
AUDIO_SAMPLE_RATE  = 44100
VIDEO_BITRATE      = "8M"
AUDIO_BITRATE      = "192k"

# ── Subtitle Styling (Advanced SubStation Alpha .ass) ─────────────────────────
SUBTITLE_FONT_NAME    = os.getenv("SUBTITLE_FONT_NAME", "Arial")
SUBTITLE_FONT_SIZE    = int(os.getenv("SUBTITLE_FONT_SIZE", "18"))
SUBTITLE_PRIMARY_COL  = "&H002BF5FF&"  # Vibrant gold-yellow (BGR format)
SUBTITLE_OUTLINE_COL  = "&H00000000&"  # Solid black outline
SUBTITLE_OUTLINE_SIZE = 2
SUBTITLE_MARGIN_V     = 280            # Vertical margin from bottom safe zone

# ── Meta / Instagram Graph API Configuration ──────────────────────────────────
IG_USER_ID       = os.getenv("IG_USER_ID", "")
IG_ACCESS_TOKEN  = os.getenv("IG_ACCESS_TOKEN", "")
META_API_VERSION = os.getenv("META_API_VERSION", "v21.0")

# ── Default Content Niche ─────────────────────────────────────────────────────
DEFAULT_NICHE = os.getenv("DEFAULT_NICHE", "Cinematic Curiosities & Lost History")

# ── Autonomous Production Daemon Scheduling ───────────────────────────────────
DAILY_PREP_HOUR    = int(os.getenv("DAILY_PREP_HOUR", "9"))     # 09:00 AM
DAILY_PREP_MINUTE  = int(os.getenv("DAILY_PREP_MINUTE", "0"))
SCHEDULE_TIMEZONE  = os.getenv("SCHEDULE_TIMEZONE", "Asia/Kolkata")
