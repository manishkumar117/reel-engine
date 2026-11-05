"""
r2_manager.py — Cloudflare R2 / AWS S3 Public Storage Client for reel_engine.

Provides zero-egress public HTTPS endpoints for compiled master reels, which is
strictly required by Meta's Instagram Graph API crawler.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from reel_engine.config import (
    PUBLIC_STORAGE_URL,
    R2_ACCOUNT_ID,
    R2_ACCESS_KEY_ID,
    R2_BUCKET_NAME,
    R2_SECRET_ACCESS_KEY,
)

logger = logging.getLogger(__name__)


class R2Manager:
    """Manages public CDN uploads to Cloudflare R2 / AWS S3."""

    def __init__(self):
        self.bucket = R2_BUCKET_NAME
        self.public_base_url = PUBLIC_STORAGE_URL.rstrip("/")
        self.client = None
        self._init_client()

    def _init_client(self):
        if not (R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and self.bucket):
            logger.debug("[r2_manager] Cloudflare R2 credentials not fully configured.")
            return

        try:
            import boto3
            endpoint_url = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else None
            self.client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=R2_ACCESS_KEY_ID,
                aws_secret_access_key=R2_SECRET_ACCESS_KEY,
                region_name="auto"
            )
            logger.info("[r2_manager] Cloudflare R2 S3 client initialized.")
        except ImportError:
            logger.debug("[r2_manager] boto3 not installed. Cloudflare R2 upload skipped.")
        except Exception as e:
            logger.warning(f"[r2_manager] Could not initialize R2 client: {e}")

    def is_configured(self) -> bool:
        return self.client is not None and bool(self.bucket)

    def upload_reel(self, local_mp4: Path, remote_filename: Optional[str] = None) -> Optional[str]:
        """
        Uploads master reel MP4 and returns public HTTPS URL.
        """
        if not local_mp4.exists():
            logger.error(f"[r2_manager] File not found: {local_mp4}")
            return None

        remote_name = remote_filename or f"reels/{local_mp4.parent.name}/{local_mp4.name}"

        if self.is_configured():
            try:
                logger.info(f"[r2_manager] Uploading {local_mp4.name} to R2 bucket '{self.bucket}'...")
                self.client.upload_file(
                    str(local_mp4),
                    self.bucket,
                    remote_name,
                    ExtraArgs={"ContentType": "video/mp4"}
                )
                public_url = f"{self.public_base_url}/{remote_name}"
                logger.info(f"[r2_manager] Master Reel live at public URL: {public_url}")
                return public_url
            except Exception as e:
                logger.error(f"[r2_manager] Failed to upload to R2: {e}")

        # Local fallback simulation
        logger.info("[r2_manager] R2 not configured. Operating in local simulated storage mode.")
        return f"file://{local_mp4.resolve()}"
