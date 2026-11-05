"""
aligner.py — Word-level subtitle generator and kinetic ASS styler.
Produces high-visibility, mobile-optimized captions positioned safely
above Instagram's UI interface elements.
"""

import logging
import math
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def generate_subtitles(storyboard: Dict[str, Any], audio_wav: Path, output_ass: Path) -> bool:
    """
    Generates an Advanced SubStation Alpha (.ass) subtitle file formatted
    for short-form vertical video (1080x1920).
    """
    output_ass.parent.mkdir(parents=True, exist_ok=True)
    
    # 1. Attempt faster-whisper if available locally
    cues = try_whisper_alignment(audio_wav)
    
    # 2. If whisper is not installed, interpolate rhythmically from storyboard scenes
    if not cues:
        cues = interpolate_scene_cues(storyboard)

    # 3. Write ASS formatted file
    write_ass_file(cues, output_ass)
    return output_ass.exists()


def try_whisper_alignment(audio_wav: Path) -> List[Dict[str, Any]]:
    """
    Extracts word timestamps via faster-whisper or whisper if installed.
    """
    cues = []
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base.en", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio_wav), word_timestamps=True)
        
        for segment in segments:
            # Chunk words into digestible 3-5 word clusters for quick reading
            chunk_words = []
            chunk_start = None
            
            for word in segment.words:
                if chunk_start is None:
                    chunk_start = word.start
                chunk_words.append(word.word.strip())
                
                if len(chunk_words) >= 4 or word.word.endswith((".", "!", "?", ",")):
                    cues.append({
                        "start": chunk_start,
                        "end": word.end,
                        "text": " ".join(chunk_words).upper()
                    })
                    chunk_words = []
                    chunk_start = None
                    
            if chunk_words:
                cues.append({
                    "start": chunk_start,
                    "end": segment.end,
                    "text": " ".join(chunk_words).upper()
                })
        logger.info(f"[aligner] Whisper extracted {len(cues)} subtitle cues.")
        return cues
    except ImportError:
        logger.debug("[aligner] faster-whisper not installed; using rhythm interpolator.")
    except Exception as e:
        logger.warning(f"[aligner] Whisper error: {e}")
    return []


def interpolate_scene_cues(storyboard: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Rhythmic speech interpolator: breaks each scene's narration into 3-4 word
    chunks timed smoothly across the scene's duration.
    """
    cues = []
    current_time = 0.2  # initial 200ms padding
    
    for scene in storyboard.get("scenes", []):
        text = scene.get("voiceover_text", "").strip()
        duration = float(scene.get("duration_secs", 6.0))
        words = text.split()
        if not words:
            current_time += duration
            continue

        # Split into micro-phrases of 3 to 4 words
        phrase_size = 4
        phrases = [" ".join(words[i:i + phrase_size]).upper() for i in range(0, len(words), phrase_size)]
        
        time_per_phrase = (duration - 0.4) / max(len(phrases), 1)
        
        for phrase in phrases:
            start = current_time
            end = start + time_per_phrase
            cues.append({
                "start": start,
                "end": end,
                "text": phrase
            })
            current_time = end
            
        current_time += 0.2  # breath gap

    return cues


def format_ass_time(seconds: float) -> str:
    """
    Convert seconds float (e.g. 12.345) to ASS format: H:MM:SS.cs
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def write_ass_file(cues: List[Dict[str, Any]], output_path: Path):
    """
    Writes a stylized ASS file with high-impact mobile typography.
    """
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: KineticReel,Arial,62,&H002BF5FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,80,80,360,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        for cue in cues:
            start_str = format_ass_time(cue["start"])
            end_str = format_ass_time(cue["end"])
            # In ASS, PrimaryColour is active; font is bold with solid outline
            f.write(f"Dialogue: 0,{start_str},{end_str},KineticReel,,0,0,0,,{cue['text']}\n")

    logger.info(f"[aligner] Saved kinetic subtitle file: {output_path}")
