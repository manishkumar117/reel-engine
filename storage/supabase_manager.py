"""
supabase_manager.py — Supabase Cloud Storage Client for reel_engine.

Provides direct HTTPS REST upload and download for prompt manifests, scene video clips,
and compiled master reels. Generates permanent, raw public HTTPS endpoints compliant with
Meta's Instagram Graph API crawler with zero credit card requirements.
"""

import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from reel_engine.config import (
    SUPABASE_BUCKET,
    SUPABASE_SERVICE_KEY,
    SUPABASE_URL,
)

logger = logging.getLogger(__name__)


class SupabaseManager:
    """Manages cloud asset storage and public streaming URLs via Supabase Storage REST API."""

    def __init__(self):
        self.bucket = SUPABASE_BUCKET or "reel-engine"
        self.service_key = SUPABASE_SERVICE_KEY.strip() if SUPABASE_SERVICE_KEY else ""
        self.base_url = self._normalize_base_url(SUPABASE_URL)

    def _normalize_base_url(self, raw_url: str) -> str:
        """Strips /rest/v1 or other endpoints to obtain root project URL."""
        if not raw_url:
            return ""
        clean = raw_url.strip()
        if "/rest" in clean:
            clean = clean.split("/rest")[0]
        return clean.rstrip("/")

    def is_configured(self) -> bool:
        """Returns True if project URL, service key, and bucket are defined."""
        return bool(self.base_url and self.service_key and self.bucket)

    def _headers(self, content_type: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.service_key}",
            "apikey": self.service_key,
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def upload_file(self, local_path: Path, remote_path: Optional[str] = None) -> Optional[str]:
        """
        Uploads a local file (markdown manifest, still image, or video) to Supabase Storage.
        Returns the permanent direct public HTTPS URL.
        """
        if not local_path.exists():
            logger.error(f"[supabase] Local file does not exist: {local_path}")
            return None

        if not self.is_configured():
            logger.debug("[supabase] Supabase Storage credentials not configured.")
            return None

        dest_key = remote_path or f"runs/{local_path.parent.name}/{local_path.name}"
        dest_key = dest_key.lstrip("/")

        # Determine MIME type
        ctype, _ = mimetypes.guess_type(str(local_path))
        if not ctype:
            if local_path.suffix in (".mp4", ".m4v"):
                ctype = "video/mp4"
            elif local_path.suffix == ".md":
                ctype = "text/markdown; charset=UTF-8"
            elif local_path.suffix == ".json":
                ctype = "application/json"
            else:
                ctype = "application/octet-stream"

        upload_url = f"{self.base_url}/storage/v1/object/{self.bucket}/{dest_key}"
        headers = self._headers(content_type=ctype)
        headers["x-upsert"] = "true"  # Overwrite if exists

        try:
            logger.info(f"[supabase] Uploading {local_path.name} ({local_path.stat().st_size / 1024:.1f} KB) to {dest_key}...")
            with open(local_path, "rb") as f:
                file_bytes = f.read()

            resp = requests.post(upload_url, headers=headers, data=file_bytes, timeout=60)
            if resp.status_code in (200, 201):
                public_url = self.get_public_url(dest_key)
                logger.info(f"[supabase] Asset live at: {public_url}")
                return public_url
            else:
                logger.error(f"[supabase] Upload failed ({resp.status_code}): {resp.text}")
                return None
        except Exception as e:
            logger.error(f"[supabase] Upload exception for {local_path.name}: {e}")
            return None

    def get_public_url(self, remote_path: str) -> str:
        """Returns direct raw public HTTPS URL for a file in the public bucket."""
        clean_path = remote_path.lstrip("/")
        return f"{self.base_url}/storage/v1/object/public/{self.bucket}/{clean_path}"

    def download_scene_clips(self, run_id: str, local_videos_dir: Path) -> List[Path]:
        """
        Discovers and downloads user scene video clips from Supabase Storage under runs/{run_id}/videos/.
        """
        if not self.is_configured():
            return []

        local_videos_dir.mkdir(parents=True, exist_ok=True)
        list_url = f"{self.base_url}/storage/v1/object/list/{self.bucket}"
        prefix = f"runs/{run_id}/videos"
        downloaded: List[Path] = []

        try:
            payload = {"prefix": prefix, "limit": 100}
            resp = requests.post(list_url, headers=self._headers("application/json"), json=payload, timeout=15)
            if resp.status_code == 200:
                items = resp.json()
                for item in items:
                    name = item.get("name")
                    if name and name.endswith(".mp4"):
                        file_key = f"{prefix}/{name}"
                        dest = local_videos_dir / name
                        public_url = self.get_public_url(file_key)
                        get_resp = requests.get(public_url, timeout=120)
                        if get_resp.status_code == 200:
                            with open(dest, "wb") as f:
                                f.write(get_resp.content)
                            downloaded.append(dest)
                            logger.info(f"[supabase] Downloaded user scene clip: {name}")
            return sorted(downloaded)
        except Exception as e:
            logger.error(f"[supabase] Error querying clips for run {run_id}: {e}")
            return []
