"""
gemini_bridge.py — Resilient LLM bridge for viral retention scriptwriting,
storyboard generation, visual prompt engineering, and cinematic motion design.
Supports direct Google Gemini REST API (production standard), local agy CLI subprocess,
and curated deterministic fallback archetypes.
"""

import json
import logging
import os
import re
import subprocess
from typing import Any, Dict, Optional
import requests

from reel_engine.config import AGY_CMD, AGY_TIMEOUT_SECS, DEFAULT_NICHE

logger = logging.getLogger(__name__)


def ask_gemini(prompt: str, timeout: int = AGY_TIMEOUT_SECS) -> Optional[str]:
    """
    Executes prompt against Gemini.
    Priority 1: Direct Google Gemini REST API (if GEMINI_API_KEY is configured).
    Priority 2: agy CLI subprocess (if available locally).
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and gemini_key.strip():
        models_to_try = [
            os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            "gemini-2.5-flash",
            "gemini-1.5-flash",
        ]
        for model in models_to_try:
            try:
                logger.debug(f"[gemini_bridge] Querying Gemini model '{model}' ({len(prompt)} chars)...")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048}
                }
                resp = requests.post(url, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    return text.strip()
                else:
                    logger.warning(f"[gemini_bridge] Gemini REST API ({model}) returned HTTP {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                logger.warning(f"[gemini_bridge] Gemini REST request failed for {model}: {e}")

    # Fallback to agy CLI
    return ask_agy(prompt, timeout=timeout)


def ask_agy(prompt: str, timeout: int = AGY_TIMEOUT_SECS) -> Optional[str]:
    """
    Execute a prompt against the agy CLI via subprocess in print mode.
    Returns the raw string output or None if execution failed.
    """
    try:
        logger.debug(f"[gemini_bridge] Dispatching prompt ({len(prompt)} chars) to {AGY_CMD}...")
        result = subprocess.run(
            [AGY_CMD, "-p", prompt, "--effort", "low", "--disable-slash-commands", "--log-file", "/tmp/agy.log"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            logger.warning(f"[gemini_bridge] agy returned non-zero code {result.returncode}: {result.stderr[:200]}")
            return None

        response = result.stdout.strip()
        logger.debug(f"[gemini_bridge] Received response ({len(response)} chars)")
        return response

    except subprocess.TimeoutExpired:
        logger.error(f"[gemini_bridge] agy execution timed out after {timeout}s")
        return None
    except FileNotFoundError:
        logger.error(f"[gemini_bridge] '{AGY_CMD}' binary not found on system PATH.")
        return None
    except Exception as e:
        logger.error(f"[gemini_bridge] Unexpected subprocess error: {e}")
        return None


def extract_json(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    Robust JSON extraction from LLM text, handling markdown code fences.
    """
    if not raw_text:
        return None

    # 1. Direct parse attempt
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    # 2. Extract from ```json ... ``` code fence
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Greedy search for outermost curly braces
    brace_match = re.search(r"\{[\s\S]*\}", raw_text)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    logger.error("[gemini_bridge] Failed to parse JSON from raw LLM output.")
    return None


def create_storyboard(niche: str = DEFAULT_NICHE, specific_topic: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Researches a viral topic and outputs a production-ready storyboard JSON.
    Includes voiceover lines, scene timing, image prompts, and motion prompts.
    """
    topic_clause = f"Focus specifically on the topic: '{specific_topic}'." if specific_topic else f"Select the single most compelling, true curiosity or anomaly in the '{niche}' vertical."

    prompt = f"""You are the Lead Creative Director and Viral Retention Architect for short-form cinematic documentary reels (Instagram Reels / TikTok / YouTube Shorts).

{topic_clause}

Target Content Specifications:
1. Target Runtime: Exactly 35 to 45 seconds (approx. 80 to 105 spoken words).
2. The Hook (0-3s): Must present an immediate cognitive contradiction or high-stakes historical revelation that forces the viewer to stay.
3. Retention Swaps: Deconstruct the narrative into 4 to 6 distinct visual scenes (each 5 to 7 seconds).
4. Image Prompts: Detailed 9:16 vertical photorealistic prompts suitable for AI image diffusion (architectural textures, cinematic lighting, 35mm film grain, moody atmosphere, zero modern artifacts).
5. Motion Prompts: Explicit camera physics for Image-to-Video generation (e.g. "Slow cinematic push-in through torchlit stone corridor, subtle floating dust motes, 24fps filmic shutter").

You MUST return ONLY a valid, parseable JSON object with NO preamble or conversational text, adhering to this exact schema:
{{
  "title": "Short Catchy Internal Title",
  "topic": "Core historical event / wonder",
  "hook": "Spoken hook sentence",
  "estimated_duration_secs": 40,
  "caption": "Engaging Instagram caption with curiosity hook, context, and 5-8 targeted hashtags (e.g. #history #ancientmysteries #architecture #untoldhistory).",
  "music_mood": "e.g. Dark cinematic suspense drone, low rhythmic pulse",
  "scenes": [
    {{
      "scene_id": 1,
      "duration_secs": 6.0,
      "voiceover_text": "Exact voiceover lines spoken in this scene.",
      "image_prompt": "Ultra-detailed 9:16 vertical image prompt. Cinematic lighting, photorealistic textures...",
      "video_motion_prompt": "Camera motion instructions: slow push-in, parallax, floating particles, no fast pans..."
    }}
  ]
}}
"""
    raw_response = ask_gemini(prompt)
    if not raw_response:
        logger.warning("[gemini_bridge] Gemini returned empty response, generating high-retention fallback storyboard...")
        return get_fallback_storyboard()

    storyboard = extract_json(raw_response)
    if not storyboard or "scenes" not in storyboard:
        logger.warning("[gemini_bridge] Parsing failed, falling back to curated template...")
        return get_fallback_storyboard()

    return storyboard


def get_fallback_storyboard() -> Dict[str, Any]:
    """
    Deterministic, production-grade fallback storyboard in case CLI/network is offline.
    """
    return {
        "title": "The Underground Metropolis of Derinkuyu",
        "topic": "Derinkuyu Subterranean City, Cappadocia",
        "hook": "In 1963, a man knocked down a wall in his basement and discovered an underground city that housed 20,000 people.",
        "estimated_duration_secs": 38,
        "caption": "In 1963, a simple home renovation in Turkey uncovered Derinkuyu—an 18-story subterranean mega-structure carved deep into volcanic rock. Complete with ventilation shafts, wells, and giant stone disc doors, it protected 20,000 citizens from invaders. Who built the earliest layers remains an enigma.\n\n#derinkuyu #ancienthistory #lostcivilizations #subterranean #archaeology #unsolvedmysteries",
        "music_mood": "Dark atmospheric drone with low ominous sub-bass pulses",
        "scenes": [
            {
                "scene_id": 1,
                "duration_secs": 6.5,
                "voiceover_text": "In 1963, a homeowner in Turkey knocked down a wall in his basement, and found a passage that vanished into the earth.",
                "image_prompt": "Cinematic vertical 9:16 shot of a crumbling stone basement wall opening into a dark mysterious ancient subterranean cavern. Torchlight casting deep shadows, dust particles hanging in the air, 35mm film texture, anamorphic lens, 8k resolution.",
                "video_motion_prompt": "Slow steady camera dolly forward pushing through the broken stone doorway into the darkness, subtle handheld floating motion, cinematic mystery."
            },
            {
                "scene_id": 2,
                "duration_secs": 7.0,
                "voiceover_text": "He had accidentally uncovered Derinkuyu: an 18-story underground metropolis engineered deep into volcanic rock.",
                "image_prompt": "Dramatic cross-section view of a massive multi-level ancient subterranean city carved inside volcanic bedrock. Endless stone staircases, archways, and glowing torch-lit chambers stretching hundreds of feet down. Hyper-realistic, National Geographic aesthetic, 9:16 vertical.",
                "video_motion_prompt": "Slow vertical crane downward pan revealing the dizzying depth of subterranean levels and carved stone arches, soft ambient glow."
            },
            {
                "scene_id": 3,
                "duration_secs": 7.5,
                "voiceover_text": "It contained churches, stables, wineries, and ventilation shafts capable of sustaining 20,000 citizens in total secrecy.",
                "image_prompt": "Interior of an ancient underground hall carved into tufa rock. Heavy stone pillars supporting low vaulted ceilings, ancient carved clay amphoras, faint god rays piercing down from a distant ventilation shaft, dark academia mood, 9:16.",
                "video_motion_prompt": "Smooth cinematic lateral tracking shot across stone carved pillars, dust motes dancing in shafts of dim light, cinematic 24fps."
            },
            {
                "scene_id": 4,
                "duration_secs": 8.0,
                "voiceover_text": "Massive half-ton circular stone doors could only be rolled shut from the inside, sealing entire tiers from invading armies.",
                "image_prompt": "A giant circular carved stone disc door, five feet tall, sealing a narrow subterranean corridor carved from dark rough rock. Iron-hard stone texture, dramatic rim lighting from behind, ancient mystery, vertical 9:16.",
                "video_motion_prompt": "Slow dramatic push-in focusing on the massive rolling stone door, eerie shadows flickering across the textured rock face."
            },
            {
                "scene_id": 5,
                "duration_secs": 8.0,
                "voiceover_text": "Archaeologists still debate who carved the original tunnels thousands of years ago. The question is: what were they truly hiding from?",
                "image_prompt": "Looking down an impossibly deep, pitch-black ancient carved spiral staircase fading into mist and shadows. Minimal torchlight, eerie cosmic mystery atmosphere, cinematic wide vertical 9:16 composition.",
                "video_motion_prompt": "Slow continuous zoom into the abyss of the spiraling dark stairwell, darkness slowly enveloping the frame, suspenseful conclusion."
            }
        ]
    }
