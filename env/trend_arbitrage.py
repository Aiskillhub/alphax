"""趋势套利引擎

在需求爆发前发现机会：
1. Google Trends — 什么在涨但还没饱和
2. Reddit — "I wish there was a tool for..."
3. X/Twitter — 开发者真实痛点

核心指标：趋势速度 × 竞争缺口 = 套利机会分数
"""

from __future__ import annotations

import json
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class TrendSignal:
    """一个趋势信号"""
    source: str              # google_trends / reddit / twitter
    keyword: str
    category: str            # 关联的产品类别
    trend_velocity: float    # 0-1，增长有多快
    competition_gap: float   # 0-1，竞争有多少（1=完全没人做）
    arbitrage_score: float   # velocity × gap，越高越值得做
    volume: int = 0          # 搜索/提及量
    sample_text: str = ""    # 具体的用户原话
    url: str = ""
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class TrendReport:
    """一次完整的趋势扫描报告"""
    signals: list[TrendSignal]
    top_opportunity: TrendSignal | None
    market_mood: str          # "hot" / "warming" / "cold"
    recommendations: list[str]
    scanned_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TrendArbitrageEngine:
    """多源趋势扫描 → 套利机会排序"""

    def __init__(self):
        self._cache_path = config.data_dir / "trend_cache.json"
        self._history: list[TrendSignal] = []
        self._load()

    def scan(self, fossils=None, organisms=None) -> TrendReport:
        """全量扫描，返回排序后的套利机会"""
        signals = []

        # 三个外部数据源扫描
        signals += self._scan_reddit()
        signals += self._scan_twitter()

        # 内部数据回退：从化石和现有 organism 推断趋势
        if not signals:
            signals += self._scan_internal(fossils, organisms)

        # 按套利分数排序
        signals.sort(key=lambda s: s.arbitrage_score, reverse=True)

        # 去重：相同 keyword 只保留最高分
        seen = set()
        unique = []
        for s in signals:
            if s.keyword.lower() not in seen:
                seen.add(s.keyword.lower())
                unique.append(s)

        top = unique[0] if unique else None
        mood = self._assess_mood(unique)
        recommendations = self._generate_recommendations(unique[:5])

        self._history.extend(unique[:10])
        self._save()

        return TrendReport(
            signals=unique[:20],
            top_opportunity=top,
            market_mood=mood,
            recommendations=recommendations,
        )

    def _scan_reddit(self) -> list[TrendSignal]:
        """扫描 Reddit 上的工具需求和痛点"""
        signals = []
        subreddits = [
            ("SideProject", "dev_tools"),
            ("SaaS", "saas_boilerplate"),
            ("chrome_extensions", "chrome_extension"),
            ("productivity", "productivity"),
            ("AI_Tools", "ai_agent"),
        ]

        for sub, cat in subreddits:
            try:
                url = f"https://www.reddit.com/r/{sub}/hot.json?limit=15"
                req = urllib.request.Request(url, headers={
                    "User-Agent": "NexusTrendEngine/1.0",
                })
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                    posts = data.get("data", {}).get("children", [])

                    for post in posts:
                        pdata = post.get("data", {})
                        title = pdata.get("title", "")
                        selftext = pdata.get("selftext", "")
                        text = f"{title} {selftext}".lower()
                        score = pdata.get("score", 0)
                        num_comments = pdata.get("num_comments", 0)

                        # 检测需求信号
                        velocity = self._calc_velocity(score, num_comments)
                        gap = self._calc_gap(text)

                        if velocity > 0.3:  # 只保留有热度的
                            signals.append(TrendSignal(
                                source="reddit",
                                keyword=title[:100],
                                category=cat,
                                trend_velocity=velocity,
                                competition_gap=gap,
                                arbitrage_score=round(velocity * gap, 3),
                                volume=score + num_comments * 3,
                                sample_text=selftext[:200] if selftext else title,
                                url=f"https://reddit.com{pdata.get('permalink', '')}",
                            ))
            except Exception:
                pass

        return signals

    def _scan_twitter(self) -> list[TrendSignal]:
        """扫描 Twitter/X 上的开发者痛点"""
        signals = []
        # 使用 Nitter 作为公开接口（无需 API key）
        search_queries = [
            ("i wish there was a tool", "dev_tools"),
            ("someone should build", "saas_boilerplate"),
            ("why is there no", "chrome_extension"),
            ("chrome extension that", "chrome_extension"),
            ("would pay for", "ai_agent"),
        ]

        for query, cat in search_queries[:3]:  # 限制请求量
            try:
                encoded = urllib.parse.quote(query)
                url = f"https://nitter.net/search?f=tweets&q={encoded}"
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 NexusTrendEngine/1.0",
                })
                with urllib.request.urlopen(req, timeout=10) as resp:
                    html = resp.read().decode('utf-8', errors='replace')
                    # 简单估算：tweet 数量体现需求热度
                    mention_count = html.count('tweet-stats')
                    velocity = min(1.0, mention_count / 30)

                    if velocity > 0.1:
                        signals.append(TrendSignal(
                            source="twitter",
                            keyword=query,
                            category=cat,
                            trend_velocity=velocity,
                            competition_gap=0.8,  # 这种显式请求通常竞争少
                            arbitrage_score=round(velocity * 0.8, 3),
                            volume=mention_count,
                            sample_text=f'Search: "{query}" — {mention_count} estimated mentions',
                            url=url,
                        ))
            except Exception:
                pass

        return signals

    def _scan_internal(self, fossils=None, organisms=None) -> list[TrendSignal]:
        """从系统自身数据推断趋势（外部 API 不可用时的回退）"""
        signals = []
        category_scores: dict[str, list[float]] = {}

        # 从化石中分析：哪些品类最容易盈利
        if fossils:
            for f in fossils:
                cat = f.get("category", "") if isinstance(f, dict) else getattr(f, 'category', '')
                roi = f.get("roi", 0) if isinstance(f, dict) else getattr(f, 'roi', 0)
                if cat and roi:
                    if cat not in category_scores:
                        category_scores[cat] = []
                    category_scores[cat].append(roi)

        # 从活跃 organism 分析
        if organisms:
            for org in organisms:
                if isinstance(org, dict):
                    cat = org.get("category", "")
                else:
                    genome = getattr(org, 'genome', None)
                    cat = str(getattr(genome, 'category', '')) if genome else ''
                if cat:
                    if cat not in category_scores:
                        category_scores[cat] = []
                    category_scores[cat].append(1.0)  # 活着就是好信号

        for cat, scores in category_scores.items():
            avg_score = sum(scores) / len(scores)
            velocity = min(1.0, avg_score)
            gap = 0.6 if len(scores) < 3 else 0.3  # 样本少 = 竞争少 = gap 大

            signals.append(TrendSignal(
                source="internal",
                keyword=f"Opportunity in {cat}",
                category=cat,
                trend_velocity=velocity,
                competition_gap=gap,
                arbitrage_score=round(velocity * gap, 3),
                volume=len(scores),
                sample_text=f"Based on {len(scores)} data points. Avg success score: {avg_score:.2f}",
            ))

        return signals

    def _calc_velocity(self, score: int, comments: int) -> float:
        """根据互动量估算趋势速度 0-1"""
        engagement = score + comments * 3
        if engagement > 500:
            return 0.9
        elif engagement > 100:
            return 0.6
        elif engagement > 30:
            return 0.4
        elif engagement > 10:
            return 0.2
        return 0.05

    def _calc_gap(self, text: str) -> float:
        """估算竞争缺口：文本中越少提到已有产品，gap 越大"""
        competition_signals = [
            "existing tool", "already exists", "similar to", "competitor",
            "alternative to", "like X but", "there's already",
            "extension for this", "plugin that does", "tool that does",
        ]
        matches = sum(1 for kw in competition_signals if kw in text)
        # 有关键词 → 说明有人已经做了 → gap 小
        if matches >= 3:
            return 0.1
        elif matches >= 1:
            return 0.4
        return 0.8  # 没人提竞争者 → 可能是蓝海

    def _assess_mood(self, signals: list[TrendSignal]) -> str:
        if not signals:
            return "cold"
        avg_velocity = sum(s.trend_velocity for s in signals[:10]) / max(1, len(signals[:10]))
        if avg_velocity > 0.5:
            return "hot"
        elif avg_velocity > 0.3:
            return "warming"
        return "cold"

    def _generate_recommendations(self, top_signals: list[TrendSignal]) -> list[str]:
        """基于趋势生成具体行动建议"""
        recs = []
        for s in top_signals[:5]:
            if s.arbitrage_score > 0.5:
                recs.append(
                    f"HIGH: Build a {s.category} targeting '{s.keyword[:60]}' "
                    f"(score={s.arbitrage_score:.2f}, velocity={s.trend_velocity:.1f}, gap={s.competition_gap:.1f})"
                )
            elif s.arbitrage_score > 0.3:
                recs.append(
                    f"MEDIUM: Monitor '{s.keyword[:60]}' in {s.category} — "
                    f"growing but check competition first"
                )
        return recs

    def get_category_opportunity(self, category: str) -> float:
        """获取某品类的综合套利分数"""
        matching = [s for s in self._history if s.category == category]
        if not matching:
            return 0.3
        return sum(s.arbitrage_score for s in matching) / len(matching)

    @property
    def hottest_categories(self) -> list[tuple[str, float]]:
        """最热的品类排序"""
        by_cat: dict[str, list[float]] = {}
        for s in self._history:
            if s.category not in by_cat:
                by_cat[s.category] = []
            by_cat[s.category].append(s.arbitrage_score)
        ranked = [(cat, sum(scores) / len(scores)) for cat, scores in by_cat.items()]
        return sorted(ranked, key=lambda x: x[1], reverse=True)

    @property
    def summary(self) -> dict:
        return {
            "signals_today": len([s for s in self._history
                                 if s.detected_at[:10] == datetime.now(timezone.utc).isoformat()[:10]]),
            "total_signals": len(self._history),
            "hottest_categories": self.hottest_categories[:5],
            "market_mood": self._assess_mood(self._history[-20:]),
        }

    def _save(self):
        try:
            data = [
                {
                    "source": s.source, "keyword": s.keyword, "category": s.category,
                    "trend_velocity": s.trend_velocity, "competition_gap": s.competition_gap,
                    "arbitrage_score": s.arbitrage_score, "volume": s.volume,
                    "sample_text": s.sample_text[:200], "url": s.url, "detected_at": s.detected_at,
                }
                for s in self._history[-100:]
            ]
            self._cache_path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _load(self):
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text())
                for d in data:
                    self._history.append(TrendSignal(**d))
            except (json.JSONDecodeError, OSError):
                pass
