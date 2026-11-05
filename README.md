# Reel Engine (🎬 `reel_engine`)
### Autonomous AI Reel Production & Asynchronous Cloud Pipeline

`reel_engine` is a standalone, lightweight vertical video production microservice designed to produce high-retention short-form video content (Instagram Reels, TikTok, YouTube Shorts). 

It features an asynchronous **Human-in-the-Loop (HITL) Cloud Bridge** where the engine handles topic scouting, scripting, prompts packaging, neural voiceover, and kinetic subtitles, shares the manifest via **Google Drive and Email**, and automatically listens for your email reply with scene clips to compile the master MP4.

---

## 🏗️ Production Architecture

```
[STAGE 1: AUTONOMOUS PRE-PRODUCTION]
  python -m reel_engine.main prep [--topic "..." | --niche "..."]
       │
       ├── 1. Autonomous Topic Scout (Gemini 2.0 Flash / Anomaly Engine)
       ├── 2. Storyboard Script & Hook Architect (gemini_bridge.py)
       ├── 3. Mobile Manifests (prompts.md & storyboard.md)
       ├── 4. Neural Voiceover Synthesis (Kokoro-82M / espeak fallback)
       ├── 5. Kinetic Subtitle Generation (subtitles.ass)
       ├── 6. Google Drive Run Folder Provisioning & Prompt Upload
       └── 7. Outbound Gmail Notification Briefing (with unique [REEL-RUN-<id>] thread)

[STAGE 2: HUMAN-IN-THE-LOOP CREATIVE GENERATION]
  Principal receives email briefing on mobile / desktop:
       │
       ├── 1. Reads prompts directly in email body or opens Google Drive
       ├── 2. Renders scene clips using video models (Kling, Wan2.1, Runway, Sora)
       └── 3. Drops scene_*.mp4 into Google Drive folder OR replies "DONE" / link

[STAGE 3: INBOUND LISTENER & MASTER COMPILATION]
  python -m reel_engine.main listen (or check-replies)
       │
       ├── 1. IMAP listener ingests email reply matching [REEL-RUN-<id>]
       ├── 2. Downloads scene clips from Google Drive
       ├── 3. Normalizes clips to 1080x1920 @ 30fps
       ├── 4. Mixes voiceover & ducks background ambient audio
       ├── 5. Burns styled kinetic karaoke ASS captions
       ├── 6. Exports master MP4 (runs/<id>/final_reel.mp4)
       ├── 7. Archives to Google Drive & uploads to Cloudflare R2 (public stream)
       └── 8. Emails completion notification with video download link

[STAGE 4: DISTRIBUTION]
  python -m reel_engine.main publish --run <id> --video-url <https://...>
       │
       └── Publishes live Reel to Instagram via Meta Graph API
```

---

## 🚀 CLI Commands

### 1. Stage 1 Pre-Production
```bash
# Scout high-retention anomaly autonomously in default niche
python -m reel_engine.main prep

# Or specify a targeted topic override:
python -m reel_engine.main prep --topic "The Lost Library of Alexandria"
```

### 2. Stage 2 Video Compilation
```bash
# Compiles the latest run (or specify --run <run_folder_name>)
python -m reel_engine.main compile --run latest
```

### 3. Inbound IMAP Reply Listener Daemon
```bash
# Runs 24/7 background listener for email replies from the Principal
python -m reel_engine.main listen --interval 60

# One-shot inbox check:
python -m reel_engine.main check-replies
```

### 4. Check Pipeline Runs & States
```bash
python -m reel_engine.main status
```

### 5. Instagram Graph API Publishing (Phase 2)
```bash
python -m reel_engine.main publish --run latest --video-url "https://pub-xxxx.r2.dev/reels/run_id/final_reel.mp4"
```

---

## 📁 Repository Structure

```
reel_engine/
├── config.py                 # Central configuration and environment loader
├── main.py                   # Master orchestration CLI
├── topic_scout.py            # Standalone anomaly & curiosity scout
├── gemini_bridge.py          # Scriptwriting & prompt generation bridge
├── image_gen.py              # Prompt formatter & base visual generators
│
├── audio/
│   ├── tts_engine.py         # Kokoro-82M neural TTS & audio synthesis
│   └── background_music/     # Ambient soundtrack stems for audio ducking
│
├── subtitles/
│   └── aligner.py            # Word-level kinetic ASS subtitle generator
│
├── compiler/
│   └── video_stitcher.py     # FFmpeg normalization & master compilation
│
├── notifier/
│   ├── email_notifier.py     # Outbound Gmail SMTP briefing dispatcher
│   └── imap_listener.py      # Inbound Gmail IMAP reply monitor
│
├── storage/
│   ├── drive_manager.py      # Google Drive folder creation & clip sync
│   └── r2_manager.py         # Cloudflare R2 / S3 public video uploader
│
└── publisher/
    └── instagram_graph.py    # Meta Graph API publisher
```

---

## ⚙️ Environment Configuration (`.env`)

```bash
# AI & Intelligence
GEMINI_API_KEY=your_gemini_api_key_here

# Gmail SMTP / IMAP
GMAIL_ADDRESS=your_sender_address@gmail.com
GMAIL_APP_PASSWORD=your_16_character_app_password
ALERT_RECIPIENT=your_alert_recipient@gmail.com
IMAP_POLL_INTERVAL_SECS=60

# Google Drive HITL Hub
GDRIVE_SERVICE_ACCOUNT_FILE=service_account.json
GDRIVE_MASTER_FOLDER_ID=your_gdrive_folder_id

# Cloudflare R2 / S3 (Public Video CDN for Meta Graph API)
R2_ACCOUNT_ID=your_cloudflare_account_id
R2_ACCESS_KEY_ID=your_r2_access_key_id
R2_SECRET_ACCESS_KEY=your_r2_secret_access_key
R2_BUCKET_NAME=reel-engine-media
PUBLIC_STORAGE_URL=https://pub-xxxx.r2.dev
```
