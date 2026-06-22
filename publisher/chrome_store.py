"""AlphaX Publisher — Chrome Web Store 发布

通过 Chrome Web Store API 提交扩展。
使用 OAuth 2.0 认证，支持新建/更新。

参考: https://developer.chrome.com/docs/webstore/using_webstore_api
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path

from config import config


@dataclass
class ChromePublishResult:
    success: bool
    item_id: str = ""
    status: str = ""       # "published" | "pending" | "draft"
    error: str = ""
    dry_run: bool = False


class ChromeStorePublisher:
    """Chrome Web Store 发布器"""

    _api_base = "https://www.googleapis.com/chromewebstore/v1.1/items"

    def __init__(self, client_id: str = "", client_secret: str = "",
                 refresh_token: str = ""):
        self.client_id = client_id or getattr(config, "chrome_client_id", "")
        self.client_secret = client_secret or getattr(config, "chrome_client_secret", "")
        self.refresh_token = refresh_token or getattr(config, "chrome_refresh_token", "")
        self._access_token: str = ""

    def publish(self, zip_path: Path, organism_id: str,
                public: bool = False) -> ChromePublishResult:
        """发布/更新扩展"""
        if not self._can_publish:
            return ChromePublishResult(
                success=True,
                item_id=f"dry_cws_{organism_id}",
                status="draft",
                dry_run=True,
            )

        try:
            self._ensure_token()

            # Step 1: 上传
            with open(zip_path, "rb") as f:
                zip_data = f.read()

            upload_req = urllib.request.Request(
                f"{self._api_base}",
                data=zip_data,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "x-goog-api-version": "2",
                },
                method="POST",
            )
            upload_req.add_header("Content-Type", "application/zip")

            with urllib.request.urlopen(upload_req, timeout=30) as resp:
                upload_result = json.loads(resp.read())

            item_id = upload_result.get("id", "")
            if not item_id:
                return ChromePublishResult(
                    success=False,
                    error=f"Upload failed: {upload_result}",
                )

            # Step 2: 发布
            if public:
                publish_req = urllib.request.Request(
                    f"{self._api_base}/{item_id}/publish",
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "x-goog-api-version": "2",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps({"target": "default"}).encode(),
                    method="POST",
                )
                with urllib.request.urlopen(publish_req, timeout=10) as resp:
                    pub_result = json.loads(resp.read())
                status = pub_result.get("status", ["UNKNOWN"])[0].lower()
            else:
                status = "draft"

            return ChromePublishResult(
                success=True,
                item_id=item_id,
                status=status,
            )

        except urllib.error.HTTPError as e:
            return ChromePublishResult(
                success=False,
                error=f"HTTP {e.code}: {e.reason}",
            )
        except (urllib.error.URLError, OSError) as e:
            return ChromePublishResult(
                success=False,
                error=str(e),
            )

    def get_status(self, item_id: str) -> dict:
        """查询扩展状态"""
        if not self._can_publish:
            return {"item_id": item_id, "status": "dry_run"}

        self._ensure_token()
        try:
            req = urllib.request.Request(
                f"{self._api_base}/{item_id}?projection=DRAFT",
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "x-goog-api-version": "2",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception:
            return {"item_id": item_id, "status": "unknown"}

    # ── 内部 ──

    @property
    def _can_publish(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    def _ensure_token(self):
        if not self._can_publish:
            return
        try:
            data = urllib.parse.urlencode({
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            }).encode()

            req = urllib.request.Request(
                "https://oauth2.googleapis.com/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_data = json.loads(resp.read())
            self._access_token = token_data.get("access_token", "")
        except Exception:
            pass
