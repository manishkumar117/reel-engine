"""
markdown_exporter.py — Converts storyboard JSON into structured, mobile-friendly
Markdown documents (storyboard.md, prompts.md) and plain-text briefing blocks.
"""

from pathlib import Path
from typing import Any, Dict, Tuple


def export_markdown_bundle(storyboard: Dict[str, Any], output_dir: Path) -> Tuple[Path, Path]:
    """
    Writes storyboard.md and prompts.md into output_dir.
    Returns (storyboard_md_path, prompts_md_path).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    storyboard_md_path = output_dir / "storyboard.md"
    prompts_md_path = output_dir / "prompts.md"

    storyboard_content = generate_storyboard_markdown(storyboard)
    prompts_content = generate_prompts_markdown(storyboard)

    with open(storyboard_md_path, "w", encoding="utf-8") as f:
        f.write(storyboard_content)

    with open(prompts_md_path, "w", encoding="utf-8") as f:
        f.write(prompts_content)

    return storyboard_md_path, prompts_md_path


def generate_storyboard_markdown(storyboard: Dict[str, Any]) -> str:
    """Generates an executive production storyboard document."""
    title = storyboard.get("title", "Cinematic Documentary Reel")
    topic = storyboard.get("topic", "Anomaly Discovery")
    hook = storyboard.get("hook", "")
    duration = storyboard.get("estimated_duration_secs", 40)
    caption = storyboard.get("caption", "")
    music_mood = storyboard.get("music_mood", "Atmospheric Tension")
    scenes = storyboard.get("scenes", [])

    lines = [
        f"# 🎬 Storyboard: {title}",
        f"**Topic:** {topic}  ",
        f"**Target Duration:** ~{duration}s  ",
        f"**Audio Mood:** {music_mood}  ",
        "",
        "## 🪝 The Hook",
        f"> \"{hook}\"",
        "",
        "## 📜 Complete Narrative Script",
    ]

    for s in scenes:
        sid = s.get("scene_id")
        dur = s.get("duration_secs", 6.0)
        vo = s.get("voiceover_text", "")
        lines.append(f"- **Scene {sid}** `({dur}s)`: {vo}")

    lines.extend([
        "",
        "## 📱 Draft Caption & Hashtags",
        "```text",
        caption,
        "```",
        "",
        "## 🎞️ Scene Breakdown",
        "| Scene | Timing | Key Visual Subject | Camera Motion |",
        "| :---: | :---: | :--- | :--- |"
    ])

    for s in scenes:
        sid = s.get("scene_id")
        dur = f"{s.get('duration_secs', 6.0)}s"
        img = s.get("image_prompt", "")[:75] + "..."
        mot = s.get("video_motion_prompt", "")[:60] + "..."
        lines.append(f"| {sid} | {dur} | {img} | {mot} |")

    return "\n".join(lines) + "\n"


def generate_prompts_markdown(storyboard: Dict[str, Any]) -> str:
    """
    Generates a streamlined prompt manifest formatted specifically for
    rapid mobile/desktop copy-pasting into Kling, Wan2.1, Runway, or Midjourney.
    """
    title = storyboard.get("title", "Documentary Prompts")
    scenes = storyboard.get("scenes", [])

    lines = [
        f"# 🎥 Video Generation Manifest: {title}",
        "",
        "### Workflow Instructions:",
        "1. Copy the **[Image Prompt]** into your diffusion model (Midjourney / Flux / ComfyUI).",
        "2. Drop the resulting image into your Video Model (Kling / Wan2.1 / Runway / Hailuo).",
        "3. Paste the **[Motion Prompt]** to drive the camera movement.",
        "4. Save scene clips as `scene_1.mp4`, `scene_2.mp4` etc.",
        "",
        "---",
        ""
    ]

    for s in scenes:
        sid = s.get("scene_id")
        dur = s.get("duration_secs", 6.0)
        vo = s.get("voiceover_text", "")
        img_prompt = s.get("image_prompt", "")
        motion_prompt = s.get("video_motion_prompt", "")

        lines.extend([
            f"## 🎞️ SCENE {sid} ({dur}s)",
            f"**Narration:** *\"{vo}\"*",
            "",
            "#### Image Prompt (9:16 Vertical Photorealistic):",
            "```text",
            img_prompt,
            "```",
            "",
            "#### Video Motion Prompt (Camera Physics):",
            "```text",
            motion_prompt,
            "```",
            "",
            "---",
            ""
        ])

    return "\n".join(lines)


def format_email_prompts_block(storyboard: Dict[str, Any]) -> str:
    """
    Formats scene prompts directly for inclusion in plain-text email bodies
    so the user can copy prompts right from their email client without opening attachments.
    """
    title = storyboard.get("title", "")
    hook = storyboard.get("hook", "")
    scenes = storyboard.get("scenes", [])

    lines = [
        f"TITLE: {title}",
        f"HOOK: \"{hook}\"",
        "=" * 60,
        "SCENE PROMPTS (Copy directly into Kling / Midjourney / Wan):",
        "=" * 60,
        ""
    ]

    for s in scenes:
        sid = s.get("scene_id")
        dur = s.get("duration_secs", 6.0)
        vo = s.get("voiceover_text", "")
        img = s.get("image_prompt", "")
        mot = s.get("video_motion_prompt", "")

        lines.extend([
            f"[SCENE {sid}] ({dur}s)",
            f"VOICEOVER: \"{vo}\"",
            f"IMAGE PROMPT:",
            f"{img}",
            f"MOTION PROMPT:",
            f"{mot}",
            "-" * 40,
            ""
        ])

    return "\n".join(lines)
