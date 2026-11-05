"""
imap_listener.py — Inbound Gmail IMAP Monitor for reel_engine.

Listens for user email replies referencing [REEL-RUN-<id>].
Extracts cloud storage links or completion triggers ("DONE"), matching them to active
runs to autonomously launch Stage 2 post-production compilation.
"""

import email
import imaplib
import logging
import re
import time
from email.header import decode_header
from typing import Any, Callable, Dict, List, Optional

from reel_engine.config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD, IMAP_POLL_INTERVAL_SECS

logger = logging.getLogger(__name__)

# Tracks processed email message IDs in-memory
_PROCESSED_MSG_IDS = set()


def check_for_replies() -> List[Dict[str, Any]]:
    """
    Connects to Gmail via IMAP, searches for unread replies containing [REEL-RUN-],
    and parses out the run ID and cloud link / completion signal.
    """
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        logger.warning("[imap_listener] Gmail credentials not configured. IMAP polling unavailable.")
        return []

    results: List[Dict[str, Any]] = []

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30)
        mail.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD.replace(" ", ""))
        mail.select("INBOX")

        # Search for unread messages
        status, messages = mail.search(None, "UNSEEN")
        if status != "OK" or not messages[0]:
            mail.logout()
            return []

        msg_ids = messages[0].split()
        for mid in msg_ids:
            mid_str = mid.decode()
            if mid_str in _PROCESSED_MSG_IDS:
                continue

            res, data = mail.fetch(mid, "(RFC822)")
            if res != "OK":
                continue

            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = _decode_mime_header(msg.get("Subject", ""))
            body = _extract_body(msg)

            # Check if subject or body contains REEL-RUN tag
            run_match = re.search(r"REEL-RUN-([A-Za-z0-9_\-]+)", f"{subject} {body}")
            if not run_match:
                continue

            run_id = run_match.group(1).rstrip("]")
            logger.info(f"[imap_listener] Detected reply for Run ID: '{run_id}' (Subject: '{subject}')")

            # Extract cloud storage URL if provided
            url_match = re.search(r"https?://(?:drive\.google\.com|www\.dropbox\.com|[^\s]+)", body)
            cloud_link = url_match.group(0).rstrip(".,>") if url_match else None

            # Detect "DONE" affirmative signal
            is_done = bool(re.search(r"\b(done|ready|finished|uploaded|proceed)\b", body, re.IGNORECASE))

            results.append({
                "message_id": mid_str,
                "run_id": run_id,
                "cloud_link": cloud_link,
                "is_done": is_done,
                "subject": subject,
                "body_snippet": body[:200],
            })

            _PROCESSED_MSG_IDS.add(mid_str)

        mail.logout()

    except imaplib.IMAP4.error as e:
        logger.error(f"[imap_listener] IMAP authentication or protocol error: {e}")
    except Exception as e:
        logger.error(f"[imap_listener] Unexpected error during IMAP scan: {e}")

    return results


def start_listener_loop(
    on_reply_callback: Callable[[Dict[str, Any]], None],
    poll_interval_secs: int = IMAP_POLL_INTERVAL_SECS,
    stop_event: Optional[Any] = None
):
    """
    Continuous daemon loop checking for email replies every poll_interval_secs.
    Invokes on_reply_callback when a valid reply is ingested.
    """
    logger.info(f"[imap_listener] Starting inbound email listener daemon (interval: {poll_interval_secs}s)...")

    while True:
        if stop_event and stop_event.is_set():
            logger.info("[imap_listener] Stop event received. Shutting down listener.")
            break

        try:
            replies = check_for_replies()
            for reply in replies:
                logger.info(f"[imap_listener] Triggering workflow for Run '{reply['run_id']}'...")
                on_reply_callback(reply)
        except Exception as e:
            logger.error(f"[imap_listener] Error in listener loop: {e}")

        time.sleep(poll_interval_secs)


def _decode_mime_header(header_val: str) -> str:
    """Decodes MIME encoded header strings."""
    decoded_fragments = decode_header(header_val)
    parts = []
    for frag, encoding in decoded_fragments:
        if isinstance(frag, bytes):
            parts.append(frag.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(str(frag))
    return " ".join(parts)


def _extract_body(msg: email.message.Message) -> str:
    """Recursively extracts plain text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get("Content-Disposition"))
            if ctype == "text/plain" and "attachment" not in cdispo:
                payload = part.get_payload(decode=True)
                return payload.decode("utf-8", errors="replace") if payload else ""
    else:
        payload = msg.get_payload(decode=True)
        return payload.decode("utf-8", errors="replace") if payload else ""
    return ""
