"""市场观察 + 自我观察

扫描外部市场信号和内部种群状态，生成 ObservationLog。
这是进化的"眼睛"——看到什么，才能对什么做出反应。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import urllib.request
import urllib.error

from config import config


@dataclass
class MarketSignal:
    """一条外部市场信号"""
    source: str          # github_trending / producthunt / gumroad
    category: str        # dev_tools / ai / productivity / ...
    metric: str          # stars / upvotes / sales
    value: float
    url: str = ""
    title: str = ""


@dataclass
class SelfSignal:
    """一条内部状态信号"""
    organism_id: str
    state: str
    energy: float
    days_alive: int
    total_earned: float
    genome_summary: str


@dataclass
class ObservationLog:
    """一天的完整观察记录"""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    market_signals: list[MarketSignal] = field(default_factory=list)
    self_signals: list[SelfSignal] = field(default_factory=list)
    tool_usage: dict = field(default_factory=dict)  # tool_name → call_count
    errors: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (
            f"Market signals: {len(self.market_signals)} | "
            f"Self signals: {len(self.self_signals)} | "
            f"Errors: {len(self.errors)}"
        )


class Observer:
    """扫描内外环境，生成每日观察"""

    def __init__(self):
        self._cache_path = config.data_dir / "observation_log.jsonl"

    def scan(self, population: dict | None = None) -> ObservationLog:
        """执行完整扫描"""
        log = ObservationLog()

        # 市场扫描（多数据源）
        log.market_signals = (
            self._scan_github_trending()
            + self._scan_producthunt()
            + self._scan_chrome_store()
            + self._scan_agistore()
        )

        # 自我扫描
        if population:
            log.self_signals = self._scan_self(population)

        # 持久化
        self._append_log(log)
        return log

    # ── 市场扫描 ──

    def _scan_github_trending(self) -> list[MarketSignal]:
        """爬 GitHub Trending，提取热门品类"""
        signals = []
        try:
            url = "https://github.com/trending?since=weekly"
            req = urllib.request.Request(url, headers={"User-Agent": "Nexus/1.0", "Accept": "application/json"})
            # Try the API endpoint for structured data
            api_req = urllib.request.Request(
                "https://api.github.com/search/repositories?q=stars:>100+pushed:>2025-01-01&sort=stars&order=desc&per_page=10",
                headers={"User-Agent": "Nexus/1.0", "Accept": "application/vnd.github.v3+json"},
            )
            with urllib.request.urlopen(api_req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            for repo in data.get("items", []):
                cat = self._infer_category(repo)
                signals.append(MarketSignal(
                    source="github_trending",
                    category=cat,
                    metric="stars",
                    value=repo.get("stargazers_count", 0),
                    url=repo.get("html_url", ""),
                    title=repo.get("full_name", ""),
                ))
        except Exception:
            pass
        return signals

    def _infer_category(self, repo: dict) -> str:
        """从 repo 信息推断品类"""
        text = (
            (repo.get("description") or "") + " " +
            (repo.get("language") or "") + " " +
            " ".join(repo.get("topics", []))
        ).lower()
        if any(k in text for k in ["ai", "llm", "gpt", "agent", "mcp", "model context protocol"]):
            return "ai_agent"
        if any(k in text for k in ["dev", "tool", "sdk", "api", "framework", "cli"]):
            return "dev_tools"
        if any(k in text for k in ["chrome", "extension", "browser", "plugin"]):
            return "chrome_extension"
        if any(k in text for k in ["data", "analytics", "pipeline", "etl"]):
            return "data"
        if any(k in text for k in ["design", "ui", "component", "react", "vue"]):
            return "frontend"
        if any(k in text for k in ["security", "auth", "encrypt"]):
            return "security"
        if any(k in text for k in ["automation", "workflow", "ci/cd"]):
            return "automation"
        return "other"

    def _scan_producthunt(self) -> list[MarketSignal]:
        """爬 ProductHunt 首页趋势"""
        signals = []
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://api.producthunt.com/v2/posts?first=10&order=votes_count",
                headers={"User-Agent": "NexusObserver/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                for post in data.get("posts", [])[:10]:
                    tags = [t.get("name", "") for t in post.get("topics", [])]
                    cat = "ai_agent" if any("ai" in t.lower() for t in tags) else (
                        "dev_tools" if any("developer" in t.lower() for t in tags)
                        else tags[0] if tags else "other"
                    )
                    signals.append(MarketSignal(
                        source="producthunt",
                        category=cat,
                        metric="votes",
                        value=post.get("votes_count", 0),
                        url=post.get("url", ""),
                        title=post.get("name", ""),
                    ))
        except Exception:
            pass
        return signals

    def _scan_chrome_store(self) -> list[MarketSignal]:
        """扫描 Chrome Web Store 热门扩展类别"""
        signals = []
        try:
            import urllib.request
            categories = [
                ("productivity", "productivity"),
                ("developer", "developer-tools"),
                ("ai", "chatgpt"),
                ("automation", "automation"),
            ]
            for cat_name, query in categories[:2]:
                req = urllib.request.Request(
                    f"https://chrome.google.com/webstore/search/{query}?_category=extensions",
                    headers={"User-Agent": "NexusObserver/1.0"},
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    html = resp.read().decode('utf-8', errors='replace')
                    count = html.count('"name":"')
                    signals.append(MarketSignal(
                        source="chrome_store",
                        category=cat_name,
                        metric="listings",
                        value=min(count, 50),
                        url=f"chrome://extensions/{query}",
                        title=f"Chrome Store: {cat_name} category (~{min(count, 50)} items)",
                    ))
        except Exception:
            pass
        return signals

    def _scan_agistore(self) -> list[MarketSignal]:
        """扫描 AGIStore 市场，了解热门品类和价格分布"""
        signals = []
        if not config.agistore_api_url:
            return signals
        try:
            url = f"{config.agistore_api_url.rstrip('/')}/api/skills?sort=popular&limit=20"
            req = urllib.request.Request(url, headers={"User-Agent": "NexusObserver/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            skills = data.get("skills", data.get("data", []))
            if isinstance(skills, dict):
                skills = list(skills.values())
            for sk in (skills or [])[:20]:
                signals.append(MarketSignal(
                    source="agistore",
                    category=sk.get("category", "other"),
                    metric="downloads",
                    value=sk.get("downloads", 0),
                    url=f"{config.agistore_api_url.rstrip('/')}/skills/{sk.get('slug', '')}",
                    title=sk.get("name", ""),
                ))
        except Exception:
            pass
        return signals

    # ── 自我观察 ──

    def _scan_self(self, population: dict | list) -> list[SelfSignal]:
        """观察种群内部状态"""
        signals = []
        if isinstance(population, dict):
            items = population.items()
        else:
            items = ((p.get("organism_id", str(i)), p) for i, p in enumerate(population))

        for oid, org in items:
            if isinstance(org, dict):
                signals.append(SelfSignal(
                    organism_id=oid,
                    state=org.get("state", "?"),
                    energy=org.get("energy", 0),
                    days_alive=org.get("days_alive", 0),
                    total_earned=org.get("total_earned", 0),
                    genome_summary=org.get("genome_summary", "unknown"),
                ))
            else:
                genome = getattr(org, 'genome', None)
                summary = ""
                if genome:
                    summary = f"{getattr(genome, 'product_type', '?')}/{getattr(genome, 'category', '?')} @ ${getattr(genome, 'price_point', 0)}"
                signals.append(SelfSignal(
                    organism_id=oid,
                    state=str(getattr(org, 'state', '?')),
                    energy=getattr(org, 'energy', 0),
                    days_alive=getattr(org, 'days_alive', 0),
                    total_earned=getattr(org, 'total_earned', 0),
                    genome_summary=summary,
                ))
        return signals

    def _append_log(self, log: ObservationLog):
        """追加到日志文件"""
        try:
            entry = {
                "timestamp": log.timestamp,
                "market_count": len(log.market_signals),
                "self_count": len(log.self_signals),
                "errors": log.errors,
                "market_categories": list(set(s.category for s in log.market_signals)),
            }
            with open(self._cache_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass
