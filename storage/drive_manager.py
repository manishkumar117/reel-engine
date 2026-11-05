"""
drive_manager.py — Google Drive Cloud Integration for reel_engine.

Provides headless automated folder provisioning, prompt manifest uploads,
and scene clip downloads. Uses pure HTTPS REST API v3 with OpenSSL RS256 token exchange
(zero external SDK dependencies required) and falls back to Local-Cloud mock mode if offline.
"""

import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests

from reel_engine.config import (
    BASE_DIR,
    GDRIVE_MASTER_FOLDER_ID,
    GDRIVE_SERVICE_ACCOUNT_FILE,
)

logger = logging.getLogger(__name__)


class DriveManager:
    """Manages cloud asset exchanges via Google Drive v3 REST API or local cloud mock."""

    def __init__(self):
        self.service_account_path = self._resolve_service_account_path()
        self.master_folder_id = GDRIVE_MASTER_FOLDER_ID
        self.access_token = None
        self.token_expiry = 0
        self._init_token()

    def _resolve_service_account_path(self) -> Optional[Path]:
        """Looks for service account JSON in configured path or project root."""
        candidates = [
            Path(GDRIVE_SERVICE_ACCOUNT_FILE) if GDRIVE_SERVICE_ACCOUNT_FILE else None,
            BASE_DIR / "service_account.json",
            BASE_DIR.parent / "service_account.json",
        ]
        for p in candidates:
            if p and p.exists() and p.is_file():
                return p
        return None

    def _init_token(self):
        """Attempts to obtain Google OAuth2 access token using the service account JSON."""
        if not self.service_account_path:
            logger.info("[drive_manager] No service_account.json found. Operating in Local-Cloud Dev Mode.")
            return

        try:
            token = self._fetch_access_token()
            if token:
                self.access_token = token
                logger.info("[drive_manager] Google Drive OAuth2 token successfully acquired.")
        except Exception as e:
            logger.warning(f"[drive_manager] Failed to acquire Google Drive token: {e}. Falling back to dev mode.")

    def _fetch_access_token(self) -> Optional[str]:
        """Generates RS256 JWT assertion and exchanges it for a Google OAuth2 Bearer token."""
        with open(self.service_account_path, "r", encoding="utf-8") as f:
            sa = json.load(f)

        client_email = sa.get("client_email")
        private_key = sa.get("private_key")
        token_uri = sa.get("token_uri", "https://oauth2.googleapis.com/token")

        if not client_email or not private_key:
            return None

        # 1. Build JWT Header & Claims
        header = {"alg": "RS256", "typ": "JWT"}
        now = int(time.time())
        claims = {
            "iss": client_email,
            "scope": "https://www.googleapis.com/auth/drive",
            "aud": token_uri,
            "exp": now + 3600,
            "iat": now,
        }

        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

        header_b64 = b64url(json.dumps(header).encode("utf-8"))
        claims_b64 = b64url(json.dumps(claims).encode("utf-8"))
        signing_input = f"{header_b64}.{claims_b64}".encode("ascii")

        # 2. Sign using openssl CLI
        with tempfile.NamedTemporaryFile("w", delete=False) as key_file:
            key_file.write(private_key)
            key_path = key_file.name

        try:
            proc = subprocess.run(
                ["openssl", "dgst", "-sha256", "-sign", key_path],
                input=signing_input,
                capture_output=True,
                check=True,
            )
            signature_b64 = b64url(proc.stdout)
        finally:
            if os.path.exists(key_path):
                os.remove(key_path)

        jwt_assertion = f"{header_b64}.{claims_b64}.{signature_b64}"

        # 3. Exchange JWT for access token
        resp = requests.post(
            token_uri,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": jwt_assertion,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            self.token_expiry = now + int(data.get("expires_in", 3600)) - 60
            return data.get("access_token")
        else:
            logger.warning(f"[drive_manager] Google OAuth2 error {resp.status_code}: {resp.text}")
            return None

    def is_cloud_enabled(self) -> bool:
        """Returns True if live Google Drive API token is active."""
        if self.access_token and time.time() > self.token_expiry:
            self.access_token = self._fetch_access_token()
        return self.access_token is not None

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def create_run_folder(self, run_name: str, local_run_dir: Path) -> Tuple[str, str]:
        """
        Creates a dedicated folder for the run inside the master directory.
        Returns: (folder_id, web_view_link)
        """
        if self.is_cloud_enabled():
            try:
                metadata = {
                    "name": run_name,
                    "mimeType": "application/vnd.google-apps.folder",
                }
                if self.master_folder_id:
                    metadata["parents"] = [self.master_folder_id]

                url = "https://www.googleapis.com/drive/v3/files?fields=id,webViewLink"
                resp = requests.post(url, headers=self._headers(), json=metadata, timeout=15)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    folder_id = data.get("id")
                    link = data.get("webViewLink") or f"https://drive.google.com/drive/folders/{folder_id}"
                    logger.info(f"[drive_manager] Created live Google Drive run folder: {link}")
                    return folder_id, link
                else:
                    logger.error(f"[drive_manager] Google Drive folder create failed ({resp.status_code}): {resp.text}")
            except Exception as e:
                logger.error(f"[drive_manager] Error creating Drive folder: {e}")

        # Local-Cloud Mock Mode for Dev Phase
        mock_cloud_dir = local_run_dir / "cloud_drive"
        mock_cloud_dir.mkdir(parents=True, exist_ok=True)
        folder_id = f"local_mock_{local_run_dir.name}"
        web_link = f"file://{mock_cloud_dir.resolve()}"
        logger.info(f"[drive_manager] Operating in Local Cloud Mock: {web_link}")
        return folder_id, web_link

    def upload_file(self, folder_id: str, file_path: Path, local_run_dir: Path) -> Optional[str]:
        """Uploads a prompt manifest or media file to the cloud folder."""
        if not file_path.exists():
            logger.warning(f"[drive_manager] File to upload does not exist: {file_path}")
            return None

        if self.is_cloud_enabled() and not folder_id.startswith("local_mock_"):
            try:
                # Multipart upload for metadata + content
                metadata = {"name": file_path.name, "parents": [folder_id]}
                upload_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,webViewLink"
                
                with open(file_path, "rb") as f:
                    file_bytes = f.read()

                boundary = "-------314159265358979323846"
                body = (
                    f"--{boundary}\r\n"
                    f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                    f"{json.dumps(metadata)}\r\n"
                    f"--{boundary}\r\n"
                    f"Content-Type: application/octet-stream\r\n\r\n"
                ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

                headers = {
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": f"multipart/related; boundary={boundary}",
                }
                resp = requests.post(upload_url, headers=headers, data=body, timeout=60)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    link = data.get("webViewLink") or f"https://drive.google.com/file/d/{data.get('id')}/view"
                    logger.info(f"[drive_manager] Uploaded {file_path.name} to Drive: {link}")
                    return link
                else:
                    logger.error(f"[drive_manager] Upload failed ({resp.status_code}): {resp.text}")
            except Exception as e:
                logger.error(f"[drive_manager] Upload exception: {e}")

        # Local mock upload fallback
        mock_cloud_dir = local_run_dir / "cloud_drive"
        mock_cloud_dir.mkdir(parents=True, exist_ok=True)
        dest = mock_cloud_dir / file_path.name
        if dest != file_path:
            shutil.copy2(file_path, dest)
        return f"file://{dest.resolve()}"

    def download_scene_clips(self, folder_id_or_url: str, local_run_dir: Path) -> List[Path]:
        """
        Discovers and syncs scene_*.mp4 video clips from the cloud folder into local_run_dir/videos.
        """
        target_videos_dir = local_run_dir / "videos"
        target_videos_dir.mkdir(parents=True, exist_ok=True)
        downloaded_clips: List[Path] = []

        if self.is_cloud_enabled() and not folder_id_or_url.startswith("local_mock_"):
            try:
                folder_id = self._extract_folder_id(folder_id_or_url)
                query = f"'{folder_id}' in parents and mimeType contains 'video/' and trashed = false"
                url = f"https://www.googleapis.com/drive/v3/files?q={query}&fields=files(id,name)"
                resp = requests.get(url, headers=self._headers(), timeout=15)
                if resp.status_code == 200:
                    files = resp.json().get("files", [])
                    for f in files:
                        fid = f["id"]
                        fname = f["name"]
                        dest = target_videos_dir / fname
                        download_url = f"https://www.googleapis.com/drive/v3/files/{fid}?alt=media"
                        file_resp = requests.get(download_url, headers=self._headers(), stream=True, timeout=120)
                        if file_resp.status_code == 200:
                            with open(dest, "wb") as out_f:
                                for chunk in file_resp.iter_content(chunk_size=8192):
                                    out_f.write(chunk)
                            downloaded_clips.append(dest)
                            logger.info(f"[drive_manager] Downloaded clip: {fname}")
                    return sorted(downloaded_clips)
            except Exception as e:
                logger.error(f"[drive_manager] Download error: {e}")

        # Check local mock cloud folder
        mock_cloud_dir = local_run_dir / "cloud_drive"
        if mock_cloud_dir.exists():
            for mp4 in sorted(mock_cloud_dir.glob("*.mp4")):
                dest = target_videos_dir / mp4.name
                if dest != mp4:
                    shutil.copy2(mp4, dest)
                downloaded_clips.append(dest)

        # Also discover any clips dropped directly in local videos dir
        for mp4 in sorted(target_videos_dir.glob("*.mp4")):
            if mp4 not in downloaded_clips and not mp4.name.startswith("kenburns_"):
                downloaded_clips.append(mp4)

        return sorted(downloaded_clips)

    def _extract_folder_id(self, url_or_id: str) -> str:
        """Extracts Google Drive folder ID from a full sharing URL or returns raw ID."""
        if "folders/" in url_or_id:
            return url_or_id.split("folders/")[1].split("?")[0].strip("/")
        return url_or_id.strip()
