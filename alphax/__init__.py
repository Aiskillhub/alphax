"""AlphaX SDK — 自主进化 AI

Usage:
  from alphax import AlphaX
  ax = AlphaX("sk-xxx")
  result = ax.ask("设计用户登录系统")
  result.rate(5)
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error


class Result:
    """调用结果。可直接当字符串用，也可评分反馈。"""

    def __init__(self, data: dict, client: AlphaX):
        self._data = data
        self._client = client

    @property
    def text(self) -> str:
        return self._data.get("result", "")

    @property
    def request_id(self) -> str:
        return self._data.get("request_id", "")

    @property
    def strategy(self) -> dict:
        return self._data.get("strategy", {})

    @property
    def meta(self) -> dict:
        return self._data.get("meta", {})

    def rate(self, score: int, comment: str = ""):
        """评分 1-5，驱动基因池进化"""
        return self._client.feedback(self.request_id, score, comment)

    def __str__(self):
        return self.text

    def __repr__(self):
        gen = self.strategy.get("generation", "?")
        return f"AlphaX.Result(gen={gen}, id={self.request_id[:8]})"


class AlphaX:
    """AlphaX API 客户端。

    ax = AlphaX()           # 默认 localhost
    ax = AlphaX("sk-xxx")   # 生产 API key
    """

    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key or os.environ.get("ALPHAX_API_KEY", "")
        self.base_url = (base_url
                         or os.environ.get("ALPHAX_BASE_URL", "")
                         or "http://localhost:8080")

    def ask(self, task: str, context: dict | None = None) -> Result:
        """提交任务，返回 AI 生成的最优结果"""
        body = json.dumps({"task": task, "context": context or {}}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/v1/evolve",
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            return Result(data, self)
        except urllib.error.HTTPError as e:
            msg = json.loads(e.read().decode() if e.fp else "{}")
            raise AlphaXError(e.code, msg.get("error", str(e)))
        except urllib.error.URLError as e:
            raise AlphaXError(503, f"无法连接 {self.base_url}: {e.reason}")

    def feedback(self, request_id: str, rating: int, comment: str = "") -> dict:
        """提交评分反馈，1-5 分，驱动进化"""
        body = json.dumps({
            "request_id": request_id,
            "rating": rating,
            "comment": comment,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/v1/feedback",
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            msg = json.loads(e.read().decode() if e.fp else "{}")
            raise AlphaXError(e.code, msg.get("error", str(e)))

    def health(self) -> dict:
        """查看进化状态"""
        req = urllib.request.Request(
            f"{self.base_url}/v1/health",
            headers=self._headers(),
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h


class AlphaXError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


# ── A2A Agent SDK ──
from .agent import Agent, quick_start  # noqa: E402, F401
from .bridge import Bridge   # noqa: E402, F401
from .evolve_bridge import EvolvingBridge  # noqa: E402, F401

