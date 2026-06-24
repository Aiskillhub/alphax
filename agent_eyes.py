"""AlphaX Agent Eyes — 全网数据眼

基于 Agent-Reach，给 autonomous Agent 装上 12 平台全网搜索能力。

Python 3.9 主程序通过 subprocess 调 Python 3.12 的 agent-reach。
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class WebSignal:
    """从互联网发现的信息"""
    source: str          # twitter / reddit / bilibili / xiaohongshu / youtube / web
    title: str
    content: str
    url: str = ""
    relevance: float = 0.5
    found_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentEyes:
    """给 AlphaX Agent 装上全网眼睛。

    通过 Agent-Reach 搜索 12 个平台：
    Twitter, Reddit, B站, 小红书, YouTube, GitHub, RSS, 网页, ...
    """

    PY312 = "/opt/homebrew/bin/python3.12"

    def __init__(self):
        self._available = self._check_reach()

    def _check_reach(self) -> bool:
        try:
            result = subprocess.run(
                [self.PY312, "-m", "agent_reach", "--help"],
                capture_output=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    # ═══════════════════════════════════
    # 趋势发现
    # ═══════════════════════════════════

    def search_trends(self, query: str, platforms: list[str] | None = None) -> list[WebSignal]:
        """搜索全网趋势。platforms 为空则默认搜 Twitter + Reddit + 网页。"""
        if platforms is None:
            platforms = ["twitter", "reddit", "web"]

        signals = []
        for platform in platforms:
            try:
                results = self._search(platform, query)
                signals.extend(results)
            except Exception:
                pass

        signals.sort(key=lambda s: s.relevance, reverse=True)
        return signals[:20]

    def find_pain_points(self, keyword: str) -> list[WebSignal]:
        """找用户的真实痛点。搜"wish there was"、"hate"、"hard to"等关键词。"""
        queries = [
            f"{keyword} wish there was",
            f"{keyword} hard to",
            f"{keyword} hate",
            f"looking for {keyword} tool",
        ]
        all_signals = []
        for q in queries[:2]:  # 只搜两个，避免太慢
            all_signals.extend(self.search_trends(q, ["reddit", "twitter"]))
        return sorted(all_signals, key=lambda s: s.relevance, reverse=True)[:10]

    def find_gigs(self) -> list[WebSignal]:
        """找自由职业需求。"""
        queries = [
            "need developer chrome extension",
            "looking for web tool",
            "hire freelance developer",
            "build me a",
        ]
        all_signals = []
        for q in queries[:2]:
            all_signals.extend(self.search_trends(q, ["reddit", "twitter"]))
        return sorted(all_signals, key=lambda s: s.relevance, reverse=True)[:10]

    def research_competitor(self, product_name: str) -> list[WebSignal]:
        """研究竞品。"""
        return self.search_trends(
            f"{product_name} review alternative",
            ["web", "reddit", "twitter"],
        )

    # ═══════════════════════════════════
    # 内部
    # ═══════════════════════════════════

    def _search(self, platform: str, query: str) -> list[WebSignal]:
        """调用 Agent-Reach CLI。"""
        if not self._available:
            return []

        result = subprocess.run(
            [self.PY312, "-m", "agent_reach", "search",
             "--platform", platform,
             "--query", query,
             "--max-results", "5",
             "--format", "json"],
            capture_output=True, text=True, timeout=30,
        )

        if result.returncode != 0:
            return []

        try:
            data = json.loads(result.stdout)
            items = data if isinstance(data, list) else data.get("results", [])
            signals = []
            for item in items:
                signals.append(WebSignal(
                    source=platform,
                    title=item.get("title", "")[:100],
                    content=item.get("content", item.get("text", ""))[:300],
                    url=item.get("url", ""),
                    relevance=float(item.get("relevance", 0.5)),
                ))
            return signals
        except Exception:
            return []


# ═══════════════════════════════════
# CLI 测试
# ═══════════════════════════════════

if __name__ == "__main__":
    eyes = AgentEyes()
    print(f"Agent-Reach 可用: {eyes._available}")

    if eyes._available:
        print("\n🔍 搜索 'chrome extension tool':")
        results = eyes.search_trends("chrome extension tool", ["web"])
        for r in results[:5]:
            print(f"   [{r.source}] {r.title[:80]}")
    else:
        print("   Agent-Reach 未安装（需 Python 3.12）")
