"""
tts_engine.py — High-fidelity local voiceover synthesis for reel_engine.
Supports local Kokoro-82M neural TTS, system TTS fallback (espeak-ng),
and optional ElevenLabs cloud API synthesis.
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def synthesize_script(storyboard: Dict[str, Any], output_wav: Path) -> bool:
    """
    Concatenates scene voiceover texts and synthesizes a master voiceover.wav.
    """
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    scenes = storyboard.get("scenes", [])
    if not scenes:
        logger.error("[tts_engine] No scenes found in storyboard.")
        return False

    # Build continuous narrative with natural speech pauses between scenes
    full_text = " ... ".join([s.get("voiceover_text", "").strip() for s in scenes if s.get("voiceover_text")])
    logger.info(f"[tts_engine] Synthesizing voiceover ({len(full_text.split())} words)...")

    # 1. Attempt Kokoro Local Python Engine if available
    if try_kokoro_local(full_text, output_wav):
        return True

    # 2. Attempt ElevenLabs if API key configured
    eleven_key = os.getenv("ELEVENLABS_API_KEY", "")
    if eleven_key:
        if try_elevenlabs(full_text, output_wav, eleven_key):
            return True

    # 3. Fast offline system TTS fallback (espeak-ng)
    if try_espeak(full_text, output_wav):
        return True

    # 4. Minimal tone generator if all else fails
    return create_silence_fallback(output_wav, duration=storyboard.get("estimated_duration_secs", 35))


def try_kokoro_local(text: str, output_path: Path) -> bool:
    """
    Synthesize speech using the local Kokoro-82M model if the package is installed.
    """
    try:
        from kokoro import KPipeline
        import soundfile as sf
        
        pipeline = KPipeline(lang_code='a')  # American English
        generator = pipeline(text, voice='am_eric', speed=1.05, split_pattern=r'\n+')
        
        audio_chunks = []
        for _, _, audio in generator:
            audio_chunks.append(audio)
            
        if audio_chunks:
            import numpy as np
            full_audio = np.concatenate(audio_chunks)
            sf.write(str(output_path), full_audio, 24000)
            logger.info(f"[tts_engine] Kokoro-82M generated audio: {output_path}")
            return True
    except ImportError:
        logger.debug("[tts_engine] Local 'kokoro' package not installed in active environment.")
    except Exception as e:
        logger.warning(f"[tts_engine] Kokoro synthesis error: {e}")
    return False


def try_espeak(text: str, output_path: Path) -> bool:
    """
    Fallback using espeak-ng on Linux systems for offline zero-cost rendering.
    """
    try:
        cmd = [
            "espeak-ng",
            "-v", "en-us+m3",  # Deep male American voice
            "-s", "145",        # Measured documentary pace (~145 words/min)
            "-p", "35",         # Lower pitch for documentary presence
            "-w", str(output_path),
            text
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and output_path.exists():
            logger.info(f"[tts_engine] espeak-ng voiceover generated: {output_path}")
            return True
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"[tts_engine] espeak-ng error: {e}")
    return False


def try_elevenlabs(text: str, output_path: Path, api_key: str) -> bool:
    """
    Cloud fallback using ElevenLabs API if credentials are provided.
    """
    try:
        import requests
        voice_id = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # 'Adam'
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }
        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}
        }
        resp = requests.post(url, json=data, headers=headers, timeout=30)
        if resp.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            logger.info(f"[tts_engine] ElevenLabs voiceover saved: {output_path}")
            return True
    except Exception as e:
        logger.warning(f"[tts_engine] ElevenLabs API error: {e}")
    return False


def create_silence_fallback(output_path: Path, duration: int = 35) -> bool:
    """
    Creates an empty audio stream so downstream video compilation still functions.
    """
    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(duration),
            "-acodec", "pcm_s16le",
            str(output_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception as e:
        logger.error(f"[tts_engine] Fallback silence creation failed: {e}")
        return False
