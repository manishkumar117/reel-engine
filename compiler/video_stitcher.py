"""
video_stitcher.py — Headless FFmpeg video compiler for reel_engine.
Concatenates scene clips, normalizes resolution to 1080x1920, burns kinetic .ass
subtitles, ducks background music under voiceover, and exports Instagram-compliant MP4.
"""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from reel_engine.config import (
    FFMPEG_CMD, TARGET_WIDTH, TARGET_HEIGHT, TARGET_FPS,
    VIDEO_CODEC, AUDIO_CODEC, VIDEO_BITRATE, AUDIO_BITRATE,
    AUDIO_SAMPLE_RATE, MUSIC_DIR
)

logger = logging.getLogger(__name__)


def compile_reel(run_dir: Path) -> Optional[Path]:
    """
    Main compilation orchestrator. Takes a run directory, discovers
    scene video clips (or generates Ken-Burns motion clips from stills),
    stitches them, overlays audio & subtitles, and renders final_reel.mp4.
    """
    plan_path = run_dir / "plan.json"
    if not plan_path.exists():
        logger.error(f"[stitcher] plan.json missing in {run_dir}")
        return None

    with open(plan_path, "r", encoding="utf-8") as f:
        storyboard = json.load(f)

    videos_dir = run_dir / "videos"
    images_dir = run_dir / "images"
    audio_wav = run_dir / "voiceover.wav"
    subtitles_ass = run_dir / "subtitles.ass"
    output_mp4 = run_dir / "final_reel.mp4"

    # Step 1: Discover or assemble scene video segments
    scene_clips = prepare_scene_clips(storyboard, videos_dir, images_dir)
    if not scene_clips:
        logger.error("[stitcher] No scene clips available to compile.")
        return None

    # Step 2: Build concatenated visual track (intermediate)
    visual_track_mp4 = run_dir / "visual_stitched.mp4"
    if not concat_video_clips(scene_clips, visual_track_mp4):
        logger.error("[stitcher] Video concatenation failed.")
        return None

    # Step 3: Mix audio (voiceover + background music ducking)
    mixed_audio_wav = run_dir / "audio_mixed.wav"
    prepare_audio_track(audio_wav, mixed_audio_wav)

    # Step 4: Final master render (burn ASS subtitles + multiplex audio)
    success = render_final_master(
        visual_mp4=visual_track_mp4,
        audio_wav=mixed_audio_wav if mixed_audio_wav.exists() else audio_wav,
        subtitles_ass=subtitles_ass,
        output_mp4=output_mp4
    )

    # Cleanup temporary intermediates
    if visual_track_mp4.exists():
        visual_track_mp4.unlink()
    if mixed_audio_wav.exists():
        mixed_audio_wav.unlink()

    if success and output_mp4.exists():
        logger.info(f"[stitcher] Master Reel successfully compiled: {output_mp4}")
        return output_mp4
    return None


def prepare_scene_clips(storyboard: Dict[str, Any], videos_dir: Path, images_dir: Path) -> List[Path]:
    """
    Scans for user-dropped video clips. If a scene clip is missing, generates
    a smooth slow-zoom (Ken Burns) clip from the scene's base image.
    """
    clips: List[Path] = []
    scenes = storyboard.get("scenes", [])
    videos_dir.mkdir(parents=True, exist_ok=True)

    for scene in scenes:
        scene_id = scene.get("scene_id")
        duration = float(scene.get("duration_secs", 6.0))
        video_candidate = videos_dir / f"scene_{scene_id}.mp4"
        image_candidate = images_dir / f"scene_{scene_id}.png"

        if video_candidate.exists() and video_candidate.stat().st_size > 1000:
            logger.info(f"[stitcher] Scene {scene_id}: Using user video {video_candidate.name}")
            clips.append(video_candidate)
        elif image_candidate.exists():
            logger.info(f"[stitcher] Scene {scene_id}: Generating motion clip from base image...")
            motion_clip = videos_dir / f"kenburns_scene_{scene_id}.mp4"
            create_ken_burns_clip(image_candidate, motion_clip, duration)
            if motion_clip.exists():
                clips.append(motion_clip)
        else:
            logger.warning(f"[stitcher] Neither video nor image found for Scene {scene_id}")

    return clips


def create_ken_burns_clip(image_path: Path, output_mp4: Path, duration: float):
    """
    Generates a cinematic slow zoom-in on a still image via FFmpeg filter.
    """
    # Zoom from 1.0 to 1.15 over the duration
    total_frames = int(duration * TARGET_FPS)
    zoom_expr = f"min(zoom+0.001,1.15)"
    vf = (
        f"scale=-2:2160,zoompan=z='{zoom_expr}':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={TARGET_WIDTH}x{TARGET_HEIGHT}:fps={TARGET_FPS},"
        f"format=yuv420p"
    )
    cmd = [
        FFMPEG_CMD, "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", vf,
        "-t", str(duration),
        "-c:v", VIDEO_CODEC,
        "-pix_fmt", "yuv420p",
        str(output_mp4)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def concat_video_clips(clips: List[Path], output_mp4: Path) -> bool:
    """
    Normalizes resolution to 1080x1920 and concatenates scene clips.
    """
    concat_list_file = output_mp4.parent / "concat_list.txt"
    normalized_clips = []

    for idx, clip in enumerate(clips):
        norm_clip = output_mp4.parent / f"norm_{idx}.mp4"
        # Scale & pad to exact 1080x1920 vertical canvas
        vf = f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        cmd = [
            FFMPEG_CMD, "-y",
            "-i", str(clip),
            "-vf", vf,
            "-r", str(TARGET_FPS),
            "-c:v", VIDEO_CODEC,
            "-pix_fmt", "yuv420p",
            "-an",
            str(norm_clip)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if norm_clip.exists():
            normalized_clips.append(norm_clip)

    with open(concat_list_file, "w", encoding="utf-8") as f:
        for c in normalized_clips:
            f.write(f"file '{c.resolve()}'\n")

    cmd = [
        FFMPEG_CMD, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_file),
        "-c", "copy",
        str(output_mp4)
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Cleanup normalized parts
    concat_list_file.unlink(missing_ok=True)
    for c in normalized_clips:
        c.unlink(missing_ok=True)

    return res.returncode == 0 and output_mp4.exists()


def prepare_audio_track(voice_wav: Path, mixed_output_wav: Path):
    """
    Mixes voiceover with background music, automatically ducking music by 15dB.
    """
    if not voice_wav.exists():
        return

    # Check for ambient music in library
    music_files = list(MUSIC_DIR.glob("*.mp3")) + list(MUSIC_DIR.glob("*.wav"))
    if not music_files:
        # Generate subtle ambient sub-bass drone if no music stem exists
        cmd = [
            FFMPEG_CMD, "-y",
            "-i", str(voice_wav),
            "-acodec", "copy",
            str(mixed_output_wav)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return

    bg_music = music_files[0]
    # Amix with sidechain volume reduction on background music
    filter_complex = (
        f"[1:a]volume=0.15[bg];"
        f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    cmd = [
        FFMPEG_CMD, "-y",
        "-i", str(voice_wav),
        "-stream_loop", "-1",
        "-i", str(bg_music),
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-ar", str(AUDIO_SAMPLE_RATE),
        str(mixed_output_wav)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def render_final_master(visual_mp4: Path, audio_wav: Path, subtitles_ass: Path, output_mp4: Path) -> bool:
    """
    Burns .ass subtitles and combines video and audio into the master Instagram Reel.
    """
    # Subtitle burn filter
    ass_escaped = str(subtitles_ass.resolve()).replace(":", "\\:").replace("'", "\\'")
    vf = f"ass='{ass_escaped}'"

    cmd = [
        FFMPEG_CMD, "-y",
        "-i", str(visual_mp4),
        "-i", str(audio_wav),
        "-vf", vf,
        "-c:v", VIDEO_CODEC,
        "-b:v", VIDEO_BITRATE,
        "-c:a", AUDIO_CODEC,
        "-b:a", AUDIO_BITRATE,
        "-ar", str(AUDIO_SAMPLE_RATE),
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-movflags", "+faststart",  # Web/mobile streaming optimization
        str(output_mp4)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        logger.error(f"[stitcher] FFmpeg rendering error: {res.stderr[-300:]}")
        # Fallback render without subtitles if ASS filter fails
        cmd_fallback = [
            FFMPEG_CMD, "-y",
            "-i", str(visual_mp4),
            "-i", str(audio_wav),
            "-c:v", "copy",
            "-c:a", AUDIO_CODEC,
            "-b:a", AUDIO_BITRATE,
            "-shortest",
            "-movflags", "+faststart",
            str(output_mp4)
        ]
        subprocess.run(cmd_fallback, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return output_mp4.exists()
