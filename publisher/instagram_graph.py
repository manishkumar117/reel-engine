"""
instagram_graph.py — Meta Instagram Graph API client.
Handles asynchronous video container initialization, processing status polling,
and live Reel publication.
"""

import json
import logging
import time
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from reel_engine.config import (
    IG_USER_ID, IG_ACCESS_TOKEN, META_API_VERSION, PUBLIC_STORAGE_URL
)

logger = logging.getLogger(__name__)


class InstagramPublisher:
    def __init__(self, user_id: str = IG_USER_ID, access_token: str = IG_ACCESS_TOKEN, version: str = META_API_VERSION):
        self.user_id = user_id
        self.access_token = access_token
        self.version = version
        self.base_url = f"https://graph.facebook.com/{self.version}"

    def is_configured(self) -> bool:
        return bool(self.user_id and self.access_token)

    def publish_video(self, video_url: str, caption: str) -> Optional[Dict[str, Any]]:
        """
        Executes the three-stage Instagram Reel publishing protocol.
        """
        if not self.is_configured():
            logger.error("[publisher] IG_USER_ID or IG_ACCESS_TOKEN not configured in .env.")
            return None

        # Stage 1: Initialize Media Container
        logger.info("[publisher] Initializing Instagram Reel container...")
        creation_id = self._create_container(video_url, caption)
        if not creation_id:
            return None

        # Stage 2: Poll Container Transcoding Status
        logger.info(f"[publisher] Polling container status (ID: {creation_id})...")
        if not self._poll_status(creation_id):
            return None

        # Stage 3: Publish Container Live
        logger.info(f"[publisher] Container ready. Publishing Reel to feed...")
        media_id = self._publish_container(creation_id)
        if not media_id:
            return None

        # Stage 4: Retrieve Published Media Details
        permalink = self._get_permalink(media_id)
        logger.info(f"[publisher] Reel published successfully! URL: {permalink}")
        return {
            "status": "PUBLISHED",
            "media_id": media_id,
            "permalink": permalink
        }

    def _create_container(self, video_url: str, caption: str) -> Optional[str]:
        url = f"{self.base_url}/{self.user_id}/media"
        payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": self.access_token
        }
        try:
            resp = requests.post(url, data=payload, timeout=30)
            data = resp.json()
            if resp.status_code == 200 and "id" in data:
                return data["id"]
            logger.error(f"[publisher] Container initialization failed: {data}")
        except Exception as e:
            logger.error(f"[publisher] Request error during container creation: {e}")
        return None

    def _poll_status(self, creation_id: str, timeout_secs: int = 180) -> bool:
        url = f"{self.base_url}/{creation_id}"
        params = {
            "fields": "status_code",
            "access_token": self.access_token
        }
        start_time = time.time()
        while time.time() - start_time < timeout_secs:
            try:
                resp = requests.get(url, params=params, timeout=15)
                data = resp.json()
                status = data.get("status_code")
                logger.debug(f"[publisher] Container {creation_id} status: {status}")

                if status == "FINISHED":
                    return True
                elif status == "ERROR":
                    logger.error(f"[publisher] Container processing error: {data}")
                    return False
                elif status == "EXPIRED":
                    logger.error(f"[publisher] Container expired.")
                    return False

            except Exception as e:
                logger.warning(f"[publisher] Polling check failed: {e}")

            time.sleep(5)

        logger.error(f"[publisher] Polling timed out after {timeout_secs}s")
        return False

    def _publish_container(self, creation_id: str) -> Optional[str]:
        url = f"{self.base_url}/{self.user_id}/media_publish"
        payload = {
            "creation_id": creation_id,
            "access_token": self.access_token
        }
        try:
            resp = requests.post(url, data=payload, timeout=30)
            data = resp.json()
            if resp.status_code == 200 and "id" in data:
                return data["id"]
            logger.error(f"[publisher] Media publish failed: {data}")
        except Exception as e:
            logger.error(f"[publisher] Error during media publish: {e}")
        return None

    def _get_permalink(self, media_id: str) -> str:
        url = f"{self.base_url}/{media_id}"
        params = {
            "fields": "permalink",
            "access_token": self.access_token
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            return data.get("permalink", f"https://instagram.com/p/{media_id}")
        except Exception:
            return f"https://instagram.com/p/{media_id}"
