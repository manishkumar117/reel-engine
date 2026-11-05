"""
email_notifier.py — Dispatches pre-production briefings and completion alerts.
Includes prompts directly in the email body for 1-tap mobile copying and attaches
the structured prompts.md and storyboard.md files.
"""

import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, Optional

from reel_engine.config import ALERT_RECIPIENT, GMAIL_ADDRESS, GMAIL_APP_PASSWORD
from reel_engine.storyboard.markdown_exporter import format_email_prompts_block

logger = logging.getLogger(__name__)


def send_prompts_notification(
    storyboard: Dict[str, Any],
    run_dir: Path,
    cloud_folder_link: str,
    prompts_md_path: Optional[Path] = None,
    storyboard_md_path: Optional[Path] = None,
) -> bool:
    """
    Sends the Stage 1 pre-production briefing to the principal.
    Subject includes a unique [REEL-RUN-<id>] tag for IMAP reply tracking.
    """
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        logger.warning("[notifier] Gmail credentials not configured. Email notification skipped.")
        return False

    run_id = run_dir.name
    title = storyboard.get("title", "Documentary Reel")
    hook = storyboard.get("hook", "")
    duration = storyboard.get("estimated_duration_secs", 35)

    subject = f"[REEL-RUN-{run_id}] Pre-Production Ready: {title}"

    prompts_block = format_email_prompts_block(storyboard)

    body = f"""Sir,

Autonomous pre-production for the next cinematic reel is complete and awaiting your creative direction.

RUN ID: {run_id}
TITLE: {title}
TARGET RUNTIME: ~{duration} seconds
HOOK: "{hook}"

================================================================================
CLOUD STORAGE DESTINATION (Google Drive):
{cloud_folder_link}
================================================================================

NEXT STEPS FOR HUMAN-IN-THE-LOOP CREATION:
1. Review the scene prompts below (or in the attached prompts.md).
2. Generate your video clips using your preferred AI model (Kling, Wan2.1, Runway, Sora).
3. Drop scene_1.mp4, scene_2.mp4, etc., into the Google Drive folder above.
4. Reply directly to this email with:
      DONE
   or provide an alternative cloud storage link if hosted elsewhere.

Once your reply is received, the engine will autonomously assemble the visual track,
duck the audio, burn kinetic subtitles, and compile the final master reel.

{prompts_block}

Standing by for your signal.
Reeve | Autonomous Reel Engine
"""

    return _dispatch_email(
        subject=subject,
        plain_body=body,
        run_id=run_id,
        attachments=[prompts_md_path, storyboard_md_path]
    )


def send_render_complete_notification(
    storyboard: Dict[str, Any],
    run_dir: Path,
    final_mp4_path: Path,
    cloud_download_link: Optional[str] = None
) -> bool:
    """Dispatches completion alert when the master reel is rendered."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        logger.warning("[notifier] Gmail credentials not configured. Render notification skipped.")
        return False

    run_id = run_dir.name
    title = storyboard.get("title", "Cinematic Reel")
    size_mb = final_mp4_path.stat().st_size / (1024 * 1024) if final_mp4_path.exists() else 0.0

    subject = f"[REEL-RENDERED-{run_id}] Master Reel Complete: {title}"
    link_info = f"\nCloud Download Link: {cloud_download_link}\n" if cloud_download_link else ""

    body = f"""Sir,

The master documentary reel compilation is complete and verified.

RUN ID: {run_id}
TITLE: {title}
MASTER MP4 SIZE: {size_mb:.2f} MB
SPECIFICATION: 1080x1920 Vertical (9:16), 30fps, AAC Audio + ASS Kinetic Subtitles
{link_info}
Local Master Path: {final_mp4_path.resolve()}

The video asset and caption are ready for distribution.

Respectfully,
Reeve | Autonomous Reel Engine
"""

    return _dispatch_email(
        subject=subject,
        plain_body=body,
        run_id=run_id,
        attachments=[]
    )


def _dispatch_email(
    subject: str,
    plain_body: str,
    run_id: str,
    attachments: Optional[list] = None
) -> bool:
    """Transmits email with headers and optional attachments via Gmail SMTP."""
    try:
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = f"Reeve | Reel Engine <{GMAIL_ADDRESS}>"
        msg["To"] = ALERT_RECIPIENT
        msg["X-Reel-Run-ID"] = run_id

        msg.attach(MIMEText(plain_body, "plain", "utf-8"))

        if attachments:
            for att_path in attachments:
                if att_path and Path(att_path).exists():
                    p = Path(att_path)
                    with open(p, "rb") as f:
                        part = MIMEApplication(f.read(), Name=p.name)
                    part["Content-Disposition"] = f'attachment; filename="{p.name}"'
                    msg.attach(part)

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=25) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD.replace(" ", ""))
            smtp.sendmail(GMAIL_ADDRESS, ALERT_RECIPIENT, msg.as_string())

        logger.info(f"[notifier] Delivered notification: '{subject}'")
        return True

    except Exception as e:
        logger.error(f"[notifier] Failed to dispatch email: {e}")
        return False
