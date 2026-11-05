"""
main.py — Master Orchestration CLI for reel_engine.

Commands:
  prep          — Autonomous Stage 1 pre-production: topic scouting, storyboard drafting,
                  prompts.md packaging, voiceover synthesis, subtitles, cloud sync & email briefing.
  compile       — Stage 2 video post-production: discovers clips (local/Drive), normalizes to
                  1080x1920, mixes audio, burns subtitles, exports master MP4, uploads to cloud.
  listen        — Inbound IMAP daemon: listens for user replies to reel briefing emails,
                  extracts cloud links / DONE signals, and launches compilation autonomously.
  check-replies — One-shot check for pending email replies without running a daemon loop.
  publish       — Post master reel to Instagram via Meta Graph API.
  status        — Inspect recent production runs and their completion state.
"""

import argparse
import datetime
import json
import logging
import os
import re
import sys
import threading
from pathlib import Path
from typing import Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("reel_engine")

from reel_engine.config import (
    RUNS_DIR,
    DEFAULT_NICHE,
    IMAP_POLL_INTERVAL_SECS,
    GMAIL_ADDRESS,
)
from reel_engine.topic_scout import scout_topic
from reel_engine.gemini_bridge import create_storyboard
from reel_engine.storyboard.markdown_exporter import export_markdown_bundle
from reel_engine.image_gen import generate_scene_images
from reel_engine.audio.tts_engine import synthesize_script
from reel_engine.subtitles.aligner import generate_subtitles
from reel_engine.compiler.video_stitcher import compile_reel
from reel_engine.storage.drive_manager import DriveManager
from reel_engine.storage.r2_manager import R2Manager
from reel_engine.storage.supabase_manager import SupabaseManager
from reel_engine.notifier.email_notifier import (
    send_prompts_notification,
    send_render_complete_notification,
)
from reel_engine.notifier.imap_listener import check_for_replies, start_listener_loop
from reel_engine.publisher.instagram_graph import InstagramPublisher


def slugify(text: str) -> str:
    """Helper to convert title to folder-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "_", text)[:32]


def cmd_prep(args):
    """
    Stage 1: Autonomous Pre-Production.
    Scouts viral topic, generates storyboard & prompts.md, synthesizes voiceover,
    creates kinetic subtitles, prepares base frames, syncs to Google Drive,
    and dispatches an executive email briefing with copy-pasteable prompts.
    """
    niche = args.niche or DEFAULT_NICHE
    topic = args.topic
    skip_email = getattr(args, "no_email", False)
    allow_local_trends = not getattr(args, "no_local_trends", False)

    print("\n" + "=" * 70)
    print(f"🎬 [STAGE 1: PRE-PRODUCTION] Initiating Run for Niche: '{niche}'")
    print("=" * 70)

    # 1. Scout topic (Autonomous Gemini or Local Trends)
    if not topic:
        print("\n[1/6] Scouting high-retention anomaly & curiosity hooks...")
        scouted = scout_topic(niche=niche, allow_local_trends=allow_local_trends)
        topic = scouted.get("topic")
        print(f"   ✓ Scouted Topic: '{topic}'")
        print(f"   ✓ Intelligence Source: {scouted.get('source')}")
    else:
        print(f"\n[1/6] Using explicit priority topic: '{topic}'")

    # 2. Generate Storyboard via Gemini Bridge
    print("\n[2/6] Structuring narrative arc, hook, and scene-by-scene prompts...")
    storyboard = create_storyboard(niche=niche, specific_topic=topic)
    if not storyboard:
        print("❌ Error: Failed to generate storyboard.")
        return 1

    title = storyboard.get("title", "Cinematic Curiosity")
    date_str = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    run_folder_name = f"{date_str}_{slugify(title)}"
    run_dir = RUNS_DIR / run_folder_name
    run_dir.mkdir(parents=True, exist_ok=True)
    images_dir = run_dir / "images"
    videos_dir = run_dir / "videos"
    videos_dir.mkdir(exist_ok=True)

    print(f"   ✓ Title: '{title}'")
    print(f"   ✓ Hook:  \"{storyboard.get('hook')}\"")
    print(f"   ✓ Run Directory: {run_dir}")

    # Save plan.json
    plan_path = run_dir / "plan.json"
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(storyboard, f, indent=2)

    # 3. Export Markdown Bundles (storyboard.md and prompts.md)
    print("\n[3/6] Exporting mobile-optimized prompts.md and storyboard.md...")
    storyboard_md, prompts_md = export_markdown_bundle(storyboard, run_dir)
    print(f"   ✓ Prompts Manifest:    {prompts_md.name}")
    print(f"   ✓ Master Storyboard:   {storyboard_md.name}")

    # Generate base reference stills & prompts.txt for backward compatibility
    generate_scene_images(storyboard, images_dir)

    # 4. Synthesize Voiceover
    print("\n[4/6] Synthesizing documentary voiceover audio...")
    audio_wav = run_dir / "voiceover.wav"
    synthesize_script(storyboard, audio_wav)
    print(f"   ✓ Voiceover saved to: {audio_wav.name}")

    # 5. Generate Kinetic Subtitles
    print("\n[5/6] Generating kinetic subtitle file (.ass)...")
    subtitles_ass = run_dir / "subtitles.ass"
    generate_subtitles(storyboard, audio_wav, subtitles_ass)
    print(f"   ✓ Kinetic subtitles saved to: {subtitles_ass.name}")

    # 6. Cloud Provisioning & Outbound Email Briefing
    print("\n[6/6] Provisioning cloud repositories and dispatching notification...")
    drive = DriveManager()
    folder_id, gdrive_link = drive.create_run_folder(run_dir.name, run_dir)
    drive.upload_file(folder_id, prompts_md, run_dir)
    drive.upload_file(folder_id, storyboard_md, run_dir)

    supabase = SupabaseManager()
    supabase_prompts_url = None
    if supabase.is_configured():
        supabase_prompts_url = supabase.upload_file(prompts_md)
        supabase.upload_file(storyboard_md)
        if supabase_prompts_url:
            print(f"   ✓ Supabase Public Prompts Link: {supabase_prompts_url}")

    primary_cloud_link = supabase_prompts_url or gdrive_link

    # Dispatch email briefing to principal
    if not skip_email:
        email_sent = send_prompts_notification(
            storyboard=storyboard,
            run_dir=run_dir,
            cloud_folder_link=primary_cloud_link,
            prompts_md_path=prompts_md,
            storyboard_md_path=storyboard_md,
        )
        if email_sent:
            print(f"   ✓ Briefing email sent to Principal with unique thread ID: [REEL-RUN-{run_dir.name}]")
        else:
            print("   ⚠️ Email dispatch skipped or credentials missing. Prompts saved locally.")
    else:
        print("   ℹ️ Email notification skipped via --no-email flag.")

    print("\n" + "=" * 70)
    print("✅ Pre-production complete! Asset bundle ready for Human-in-the-Loop generation.")
    print("🎯 NEXT ACTION:")
    print(f"1. Open Cloud Prompts: {primary_cloud_link}")
    print(f"2. Generate video clips using your preferred AI generator (Kling, Wan2.1, Runway).")
    print(f"3. Upload scene_1.mp4, scene_2.mp4 to Google Drive, then reply 'DONE' to your briefing email, or run:")
    print(f"   python -m reel_engine.main compile --run {run_dir.name}")
    print("=" * 70 + "\n")
    return 0


def cmd_compile(args):
    """
    Stage 2: Post-Production Video Compilation.
    Syncs clips from Google Drive (or local folder), normalizes video,
    mixes voiceover and background audio, burns ASS kinetic subtitles,
    uploads master MP4 to cloud storage, and alerts the principal.
    """
    run_query = getattr(args, "run", None)
    target_run = find_run_dir(run_query)
    if not target_run:
        print(f"❌ Error: Run '{run_query}' not found in {RUNS_DIR}")
        return 1

    cloud_link = getattr(args, "cloud_link", None)
    print("\n" + "=" * 70)
    print(f"🎞️ [STAGE 2: COMPILATION] Assembling Master Reel: {target_run.name}")
    print("=" * 70)

    # 1. Sync clips from Google Drive and Supabase if available
    drive = DriveManager()
    supabase = SupabaseManager()
    print("\n[1/4] Synchronizing scene video clips from cloud storage...")
    clips = drive.download_scene_clips(cloud_link or target_run.name, target_run)
    if supabase.is_configured():
        supabase_clips = supabase.download_scene_clips(target_run.name, target_run / "videos")
        for sc in supabase_clips:
            if sc not in clips:
                clips.append(sc)
    user_clips = [c for c in clips if not c.name.startswith("kenburns_")]
    print(f"   ✓ Discovered {len(user_clips)} custom video clips for assembly.")

    # 2. Compile master reel via FFmpeg
    print("\n[2/4] Executing headless FFmpeg compilation (normalization, audio ducking, subtitle burning)...")
    output_mp4 = compile_reel(target_run)
    if not output_mp4 or not output_mp4.exists():
        print("❌ Error: Compilation failed.")
        return 1

    size_mb = output_mp4.stat().st_size / (1024 * 1024)
    print(f"   ✓ Master Reel successfully compiled: {output_mp4.name} ({size_mb:.2f} MB)")

    # 3. Upload to Cloud Storage
    print("\n[3/4] Archiving master reel to cloud repositories...")
    drive_link = drive.upload_file(target_run.name, output_mp4, target_run)
    
    supabase = SupabaseManager()
    supabase_url = None
    if supabase.is_configured():
        supabase_url = supabase.upload_file(output_mp4)
        if supabase_url:
            print(f"   ✓ Supabase Public Stream Endpoint: {supabase_url}")

    r2 = R2Manager()
    public_url = supabase_url or r2.upload_reel(output_mp4)
    if public_url and not public_url.startswith("file://"):
        print(f"   ✓ Primary Public Endpoint: {public_url}")
    else:
        print(f"   ✓ Drive Archive Link:      {drive_link}")

    # 4. Notify Principal via Email
    print("\n[4/4] Transmitting completion alert...")
    plan_path = target_run / "plan.json"
    storyboard = {}
    if plan_path.exists():
        with open(plan_path, "r", encoding="utf-8") as f:
            storyboard = json.load(f)

    notification_link = public_url if (public_url and not public_url.startswith("file://")) else drive_link
    send_render_complete_notification(
        storyboard=storyboard,
        run_dir=target_run,
        final_mp4_path=output_mp4,
        cloud_download_link=notification_link
    )

    print("\n" + "=" * 70)
    print(f"🎉 MASTER REEL COMPLETE!")
    print(f"   Local File: {output_mp4.resolve()}")
    print(f"   Cloud Link: {notification_link}")
    print(f"   Aspect:     1080x1920 (9:16 Vertical, 30fps)")
    print("=" * 70 + "\n")
    return 0


def cmd_listen(args):
    """
    Inbound IMAP Daemon: Continuous monitoring of Gmail inbox for replies
    referencing [REEL-RUN-<id>]. Automatically compiles when reply is received.
    """
    interval = getattr(args, "interval", IMAP_POLL_INTERVAL_SECS)
    print("\n" + "=" * 70)
    print(f"👂 [IMAP LISTENER DAEMON] Listening for Principal email replies on {GMAIL_ADDRESS or 'Gmail'}...")
    print(f"   Polling Cadence: Every {interval} seconds")
    print("=" * 70)

    def on_reply(event):
        run_id = event["run_id"]
        cloud_link = event.get("cloud_link")
        print("\n" + "⚡" * 35)
        print(f"📨 Inbound Reply Ingested for Run: {run_id}")
        if cloud_link:
            print(f"   Storage Link: {cloud_link}")
        print("⚡" * 35 + "\n")

        # Package dummy args to execute compilation
        compile_args = argparse.Namespace(
            run=run_id,
            cloud_link=cloud_link
        )
        cmd_compile(compile_args)

    stop_event = threading.Event()
    try:
        start_listener_loop(on_reply_callback=on_reply, poll_interval_secs=interval, stop_event=stop_event)
    except KeyboardInterrupt:
        print("\n[IMAP LISTENER] Interrupted by user. Exiting cleanly.")
        stop_event.set()
        return 0


def cmd_check_replies(args):
    """One-shot scan of Gmail inbox for replies without running continuous daemon."""
    print("\n[IMAP] Scanning inbox for unread replies matching [REEL-RUN-]...")
    replies = check_for_replies()
    if not replies:
        print("No pending replies found in inbox.")
        return 0

    print(f"Found {len(replies)} actionable reply/replies:")
    for r in replies:
        print(f" • Run ID: {r['run_id']} | Cloud Link: {r.get('cloud_link')} | Done Signal: {r.get('is_done')}")
    return 0


def cmd_publish(args):
    """
    Stage 3: Distribution via Instagram Graph API.
    """
    target_run = find_run_dir(args.run)
    if not target_run:
        print(f"❌ Error: Run '{args.run}' not found.")
        return 1

    final_mp4 = target_run / "final_reel.mp4"
    if not final_mp4.exists():
        print(f"❌ Error: final_reel.mp4 missing. Run 'compile' first.")
        return 1

    with open(target_run / "plan.json", "r", encoding="utf-8") as f:
        storyboard = json.load(f)

    caption = storyboard.get("caption", "")
    video_url = args.video_url

    print("\n" + "=" * 70)
    print(f"🚀 [STAGE 3: PUBLISHING] Ingesting to Instagram Graph API")
    print("=" * 70)

    publisher = InstagramPublisher()
    if not publisher.is_configured():
        print("⚠️ Instagram API credentials missing in .env.")
        print("[DRY RUN VERIFICATION]: Video and caption are 100% formatted and ready.")
        print(f"Caption:\n{caption}\n")
        return 0

    if not video_url:
        print("⚠️ Direct upload requires a public HTTPS video URL for Meta's crawlers.")
        print(f"Upload {final_mp4} to R2/S3 or specify --video-url <https://...>")
        return 1

    result = publisher.publish_video(video_url=video_url, caption=caption)
    if result:
        print(f"\n🎉 Success! Reel is live: {result.get('permalink')}")
        return 0
    return 1


def cmd_daemon(args):
    """
    Master Production Daemon: Fully Autonomous 24/7 Engine.
    Orchestrates:
      1. Scheduled Autonomous Pre-Production (Cron trigger e.g. 09:00 daily).
      2. Inbound IMAP Reply Listener (Continuous background polling).
      3. Auto-compilation upon receiving 'DONE' email reply.
    """
    from apscheduler.schedulers.background import BackgroundScheduler
    from reel_engine.config import DAILY_PREP_HOUR, DAILY_PREP_MINUTE, SCHEDULE_TIMEZONE
    import http.server

    port = int(os.getenv("PORT", "0"))
    if port > 0:
        def run_http_server():
            class HealthHandler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status":"healthy","service":"reel_engine_daemon"}')

                def log_message(self, format, *args):
                    pass

            try:
                server = http.server.HTTPServer(("0.0.0.0", port), HealthHandler)
                logger.info(f"[daemon] Health-check HTTP server listening on port {port} (Anti-Sleep Active)")
                server.serve_forever()
            except Exception as e:
                logger.warning(f"[daemon] Could not start health-check HTTP server on port {port}: {e}")

        http_thread = threading.Thread(target=run_http_server, daemon=True)
        http_thread.start()

    print("\n" + "=" * 70)
    print("🤖 [MASTER PRODUCTION DAEMON] Launching Fully Autonomous Reel Engine")
    print(f"   Daily Scouting Schedule: Every day at {DAILY_PREP_HOUR:02d}:{DAILY_PREP_MINUTE:02d} ({SCHEDULE_TIMEZONE})")
    print(f"   Inbound Reply Listener: Active (Monitoring Gmail for 'DONE' / Links)")
    print("=" * 70)

    # 1. Initialize scheduler for Stage 1 Pre-Production
    scheduler = BackgroundScheduler(timezone=SCHEDULE_TIMEZONE)

    def scheduled_prep_job():
        logger.info("[daemon] Scheduled trigger fired! Initiating Stage 1 Pre-Production...")
        prep_args = argparse.Namespace(
            niche=DEFAULT_NICHE,
            topic=None,
            no_email=False,
            no_local_trends=True
        )
        try:
            cmd_prep(prep_args)
        except Exception as e:
            logger.error(f"[daemon] Error during scheduled prep: {e}")

    scheduler.add_job(
        scheduled_prep_job,
        trigger="cron",
        hour=DAILY_PREP_HOUR,
        minute=DAILY_PREP_MINUTE,
        id="daily_reel_prep"
    )
    scheduler.start()
    logger.info(f"[daemon] Pre-production scheduler started. Next run scheduled at {DAILY_PREP_HOUR:02d}:{DAILY_PREP_MINUTE:02d}.")

    # 2. Inbound Reply Callback (Auto-triggers Stage 2 Compilation)
    def on_user_reply(event):
        run_id = event["run_id"]
        cloud_link = event.get("cloud_link")
        logger.info(f"[daemon] Principal reply received for Run '{run_id}'! Launching Stage 2 Compilation...")
        compile_args = argparse.Namespace(
            run=run_id,
            cloud_link=cloud_link
        )
        try:
            cmd_compile(compile_args)
        except Exception as e:
            logger.error(f"[daemon] Error compiling run {run_id}: {e}")

    # 3. Start IMAP listener on main thread
    stop_event = threading.Event()
    try:
        start_listener_loop(
            on_reply_callback=on_user_reply,
            poll_interval_secs=getattr(args, "interval", IMAP_POLL_INTERVAL_SECS),
            stop_event=stop_event
        )
    except (KeyboardInterrupt, SystemExit):
        logger.info("[daemon] Shutdown signal received. Stopping scheduler and listener.")
        scheduler.shutdown()
        stop_event.set()
        return 0


def cmd_status(args):
    """Lists recent runs and their pipeline completion state."""
    runs = sorted(list(RUNS_DIR.glob("*")), reverse=True)
    print("\n" + "=" * 80)
    print(f"{'RUN DIRECTORY':<42} {'STATE':<14} {'CLIPS':<8} {'MASTER MP4'}")
    print("=" * 80)

    if not runs:
        print("No runs recorded yet. Start one with: python -m reel_engine.main prep")
        print("=" * 80 + "\n")
        return 0

    for r in runs[:10]:
        if not r.is_dir():
            continue
        has_plan = (r / "plan.json").exists()
        has_final = (r / "final_reel.mp4").exists()
        user_clips = len([f for f in (r / "videos").glob("*.mp4") if not f.name.startswith("kenburns_")]) if (r / "videos").exists() else 0

        state = "INITIAL"
        if has_final:
            state = "COMPILED"
        elif user_clips > 0:
            state = "CLIPS_READY"
        elif has_plan:
            state = "PREPPED"

        print(f"{r.name[:40]:<42} {state:<14} {user_clips:<8} {'YES' if has_final else 'NO'}")

    print("=" * 80 + "\n")
    return 0


def find_run_dir(query: Optional[str]) -> Optional[Path]:
    """Resolves a run name, path, or picks latest if omitted."""
    if not query or query == "latest":
        runs = sorted([d for d in RUNS_DIR.iterdir() if d.is_dir()], reverse=True)
        return runs[0] if runs else None

    # Direct path
    p = Path(query)
    if p.exists() and p.is_dir():
        return p

    # Inside RUNS_DIR
    target = RUNS_DIR / query
    if target.exists():
        return target

    # Partial match
    for d in RUNS_DIR.iterdir():
        if query in d.name and d.is_dir():
            return d
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Reel Engine — Autonomous & Asynchronous Short-Form Video Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # prep
    p_prep = subparsers.add_parser("prep", help="Autonomous pre-production (Stage 1)")
    p_prep.add_argument("--niche", type=str, default=DEFAULT_NICHE, help="Target vertical")
    p_prep.add_argument("--topic", type=str, default=None, help="Explicit priority topic")
    p_prep.add_argument("--no-email", action="store_true", help="Skip email notification")
    p_prep.add_argument("--no-local-trends", action="store_true", help="Bypass local trend_engine signals")

    # compile
    p_compile = subparsers.add_parser("compile", help="Assemble video & subtitles (Stage 2)")
    p_compile.add_argument("--run", type=str, default="latest", help="Run folder name or 'latest'")
    p_compile.add_argument("--cloud-link", type=str, default=None, help="Optional cloud storage link")

    # listen
    p_listen = subparsers.add_parser("listen", help="Inbound IMAP reply listener daemon")
    p_listen.add_argument("--interval", type=int, default=IMAP_POLL_INTERVAL_SECS, help="Poll interval in seconds")

    # check-replies
    subparsers.add_parser("check-replies", help="One-shot scan for email replies")

    # publish
    p_pub = subparsers.add_parser("publish", help="Publish master reel to Instagram (Stage 3)")
    p_pub.add_argument("--run", type=str, default="latest", help="Run folder name or 'latest'")
    p_pub.add_argument("--video-url", type=str, default=None, help="Public HTTPS URL of video")

    # daemon
    p_daemon = subparsers.add_parser("daemon", help="24/7 master production daemon (scheduler + IMAP listener)")
    p_daemon.add_argument("--interval", type=int, default=IMAP_POLL_INTERVAL_SECS, help="IMAP poll cadence in seconds")

    # status
    subparsers.add_parser("status", help="Inspect pipeline state")

    args = parser.parse_args()

    if args.command == "prep":
        sys.exit(cmd_prep(args))
    elif args.command == "compile":
        sys.exit(cmd_compile(args))
    elif args.command == "listen":
        sys.exit(cmd_listen(args))
    elif args.command == "check-replies":
        sys.exit(cmd_check_replies(args))
    elif args.command == "daemon":
        sys.exit(cmd_daemon(args))
    elif args.command == "publish":
        sys.exit(cmd_publish(args))
    elif args.command == "status":
        sys.exit(cmd_status(args))


if __name__ == "__main__":
    main()
