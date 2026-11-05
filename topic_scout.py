"""
topic_scout.py — Standalone Trend & Anomaly Scout for reel_engine.

Provides high-retention topic discovery without coupling to the full trend_engine scraper suite.
Operates statelessly in hosted production via Gemini intelligence, with an optional local
bridge to signal_pool.db during dev if available.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from reel_engine.config import BASE_DIR, DEFAULT_NICHE
from reel_engine.gemini_bridge import ask_agy, extract_json

logger = logging.getLogger(__name__)


def scout_topic(
    niche: str = DEFAULT_NICHE,
    allow_local_trends: bool = True,
    seed_topic: Optional[str] = None
) -> Dict[str, Any]:
    """
    Identifies a high-retention topic for reel pre-production.
    Order of precedence:
      1. Explicit seed_topic if passed.
      2. High-scoring anomaly from local trend_engine (if present and enabled).
      3. Autonomous Gemini Viral Anomaly Discovery.
    """
    if seed_topic:
        logger.info(f"[topic_scout] Using explicit topic: '{seed_topic}'")
        return {
            "topic": seed_topic,
            "angle": "User-specified priority topic",
            "hook_hypothesis": f"The untold truth behind {seed_topic}.",
            "source": "manual_override"
        }

    # Optional local bridge (Dev Phase only)
    if allow_local_trends:
        local_candidate = _scout_from_local_trends()
        if local_candidate:
            logger.info(f"[topic_scout] Discovered high-scoring candidate from local intel: '{local_candidate['topic']}'")
            return local_candidate

    # Autonomous Gemini Intelligence (Production standard)
    logger.info(f"[topic_scout] Scouting high-retention anomaly for niche: '{niche}' via Gemini...")
    autonomous_candidate = _scout_via_gemini(niche)
    if autonomous_candidate:
        return autonomous_candidate

    # Hardened fallback if network/LLM issues arise
    return {
        "topic": "The Secret Underground City of Derinkuyu",
        "angle": "Ancient architectural marvel discovered behind a modern basement wall",
        "hook_hypothesis": "In 1963, a man knocked down a wall in his basement and discovered an underground city for 20,000 people.",
        "source": "fallback_archive"
    }


def _scout_from_local_trends() -> Optional[Dict[str, Any]]:
    """
    Checks for a local trend_engine signal_pool.db if it exists on disk.
    Gracefully returns None if absent (e.g. in cloud deployment).
    """
    db_path = BASE_DIR.parent / "trend_engine" / "signal_pool.db"
    if not db_path.exists():
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Look for signals with score >= 80 that haven't been marked reported or can inspire reels
        cur.execute("""
            SELECT id, title, source, metric_score, gemini_flags, url
            FROM signals
            WHERE metric_score >= 80
            ORDER BY metric_score DESC, scraped_at DESC
            LIMIT 5;
        """)
        rows = cur.fetchall()
        conn.close()

        if rows:
            top = rows[0]
            return {
                "topic": top["title"],
                "angle": f"Surging market signal flagged from {top['source']} with score {top['metric_score']}",
                "hook_hypothesis": f"The hidden phenomenon disrupting {top['title']}.",
                "source": "local_trend_engine",
                "reference_url": top["url"]
            }
    except Exception as e:
        logger.debug(f"[topic_scout] Local trends query skipped: {e}")
        return None
    return None


def _scout_via_gemini(niche: str) -> Optional[Dict[str, Any]]:
    """
    Uses Gemini to identify an untold curiosity, historical anomaly, or high-retention enigma.
    """
    prompt = f"""You are the Chief Intelligence Scout for viral cinematic documentary reels.
Target Niche: '{niche}'

Find ONE specific, true, high-retention curiosity, forgotten historical discovery, or mind-bending anomaly that:
1. Immediately creates a cognitive gap (viewer cannot scroll past).
2. Has strong visual worldbuilding potential (ancient tunnels, lost artifacts, bizarre natural phenomena, forgotten inventions).
3. Is grounded in verifiable fact or intriguing documented lore.

Return ONLY a valid JSON object with NO markdown formatting or conversational filler:
{{
  "topic": "Specific name of the place, event, or mystery",
  "angle": "Why this is compelling and visually stunning",
  "hook_hypothesis": "The exact opening line that stops the scroll in 2 seconds"
}}
"""
    raw_response = ask_agy(prompt, timeout=60)
    if not raw_response:
        return None

    data = extract_json(raw_response)
    if data and "topic" in data:
        data["source"] = "gemini_autonomous"
        return data
    return None
