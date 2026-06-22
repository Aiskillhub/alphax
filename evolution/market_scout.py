"""市场侦察兵 — 爬取外部市场数据，作为进化选择压力

不需要自己卖，直接分析 Gumroad/ProductHunt 上什么好卖。
真实市场数据 → 基因池训练 → 进化有方向
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import urllib.request
import urllib.error

from config import config


@dataclass
class MarketSignal:
    """一条市场信号 = 一个品类/价格的验证数据"""
    category: str
    price: float
    sales_count: int
    rating: float
    source: str  # gumroad / producthunt / crawl


@dataclass
class MarketScout:
    """从公开市场收集进化信号"""

    signals: list[MarketSignal] = field(default_factory=list)
    _cache_path: Path = config.data_dir / "market_signals.json"

    def __post_init__(self):
        self._load()

    # ── Gumroad 公开数据 ──

    def scout_gumroad_discover(self, query: str = "") -> list[MarketSignal]:
        """爬 Gumroad Discover 页面，分析热门产品"""
        signals = []
        base_url = "https://discover.gumroad.com/"
        queries = query or "developer+tool"
        urls = [
            f"{base_url}?query={queries}&sort=top_selling",
            f"{base_url}?query=productivity&sort=top_selling",
            f"{base_url}?query=design+tool&sort=top_selling",
            f"{base_url}?query=marketing&sort=top_selling",
        ]

        for url in urls[:2]:  # 限速
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "AlphaX/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html = resp.read().decode()
                signals += self._parse_gumroad_discover(html, url)
            except Exception:
                pass
            time.sleep(1)

        self.signals += signals
        self._save()
        return signals

    def _parse_gumroad_discover(self, html: str, source: str) -> list[MarketSignal]:
        """从 HTML 中提取产品卡片信息"""
        signals = []
        import re

        # 找价格：$X.XX 或 $XX
        price_pattern = re.compile(r'\$(\d+\.?\d*)')
        # 找产品卡片块
        cards = html.split('class="product-card"')
        if len(cards) < 2:
            cards = html.split('class="card"')
        if len(cards) < 2:
            cards = html.split("<article")

        for card in cards[1:50]:
            prices = price_pattern.findall(card)
            if not prices:
                continue
            try:
                price = float(prices[0])
            except ValueError:
                continue

            # 品类推断
            cat = "dev_tools"
            card_lower = card.lower()
            if any(k in card_lower for k in ["code", "dev", "program", "api", "json"]):
                cat = "dev_tools"
            elif any(k in card_lower for k in ["design", "figma", "ui", "illustrator"]):
                cat = "content"
            elif any(k in card_lower for k in ["write", "blog", "seo", "content"]):
                cat = "content"
            elif any(k in card_lower for k in ["productivity", "task", "organize"]):
                cat = "productivity"
            elif any(k in card_lower for k in ["ai", "chat", "gpt", "automation"]):
                cat = "automation"
            elif any(k in card_lower for k in ["data", "analytics", "dashboard"]):
                cat = "data"
            elif any(k in card_lower for k in ["market", "seo", "traffic"]):
                cat = "seo"

            # 评分提取
            rating = 4.0
            stars = re.findall(r'(\d+\.?\d*)\s*(?:out of|/)\s*5', card)
            if stars:
                try:
                    rating = float(stars[0])
                except ValueError:
                    pass

            signals.append(MarketSignal(
                category=cat, price=price,
                sales_count=1, rating=rating, source="gumroad_discover",
            ))

        return signals

    # ── Product Hunt API ──

    def scout_producthunt(self, topic: str = "developer+tools") -> list[MarketSignal]:
        """爬 Product Hunt 热门产品"""
        signals = []
        try:
            url = f"https://www.producthunt.com/search?q={topic}&order=most_upvoted"
            req = urllib.request.Request(url, headers={"User-Agent": "AlphaX/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode()
            signals = self._parse_producthunt(html)
        except Exception:
            pass

        self.signals += signals
        self._save()
        return signals

    def _parse_producthunt(self, html: str) -> list[MarketSignal]:
        signals = []
        import re
        # 找投票数（替代销量）
        vote_pattern = re.compile(r'(\d+)\s*(?:upvotes?|votes?|points?)')
        blocks = html.split("styles_postCard")
        if len(blocks) < 2:
            blocks = html.split("<li")[:50]

        for block in blocks[1:30]:
            votes = vote_pattern.findall(block)
            v = int(votes[0]) if votes else 10
            cat = "dev_tools"
            b = block.lower()
            if "design" in b: cat = "content"
            elif "ai" in b or "automation" in b: cat = "automation"
            elif "productivity" in b: cat = "productivity"
            elif "data" in b: cat = "data"
            elif "seo" in b: cat = "seo"

            signals.append(MarketSignal(
                category=cat, price=0,
                sales_count=v, rating=4.0, source="producthunt",
            ))

        return signals

    # ── 将市场信号注入基因池 ──

    def feed_gene_pool(self, gene_pool) -> int:
        """把市场信号变成基因评分更新"""
        if not self.signals:
            return 0

        # 按品类聚合
        cat_stats: dict[str, list[float]] = {}
        for s in self.signals:
            if s.category not in cat_stats:
                cat_stats[s.category] = []
            cat_stats[s.category].append(s.rating)

        # 更新基因池中匹配品类的基因组评分
        updated = 0
        for gid, genome in gene_pool.gene_pool.items():
            cat = genome.category.value if hasattr(genome, 'category') else ""
            if cat in cat_stats:
                avg_rating = sum(cat_stats[cat]) / len(cat_stats[cat])
                # 市场信号越强，fitness 加成越高
                boost = 0.2 * (avg_rating / 5.0)
                genome.fitness_score = min(1.0, genome.fitness_score + boost)
                updated += 1

        return updated

    @property
    def summary(self) -> dict:
        if not self.signals:
            return {"signals": 0}
        cats = {}
        for s in self.signals:
            if s.category not in cats:
                cats[s.category] = {"count": 0, "avg_rating": 0, "total": 0}
            cats[s.category]["count"] += 1
            cats[s.category]["total"] += s.rating
        return {
            "signals": len(self.signals),
            "categories": {c: {"count": d["count"], "avg_rating": round(d["total"]/d["count"], 2)}
                          for c, d in sorted(cats.items(), key=lambda x: x[1]["count"], reverse=True)},
        }

    def _save(self):
        self._cache_path.write_text(json.dumps(
            [{"category": s.category, "price": s.price, "sales": s.sales_count,
              "rating": s.rating, "source": s.source} for s in self.signals],
            indent=2, default=str,
        ))

    def _load(self):
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text())
                self.signals = [MarketSignal(**d) for d in data]
            except (json.JSONDecodeError, OSError):
                pass
