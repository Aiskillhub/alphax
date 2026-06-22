"""多 Agent 竞争动力学

同一品类内，多个 organism 抢同一批用户。
真实内卷：价格战、用户流失、niche 饱和、优胜劣汰加速。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone

from config import config


@dataclass
class MarketNiche:
    """一个市场 niche——同一 category × product_type 组合"""
    category: str
    product_type: str
    total_demand: int = 100         # 每日总需求（下载量）
    organisms: list[str] = field(default_factory=list)  # organism_id 列表
    price_index: float = 1.0        # 平均价格水平
    saturation: float = 0.0         # 0-1，越高越难拿用户
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    @property
    def competitor_count(self) -> int:
        return len(self.organisms)

    @property
    def demand_per_organism(self) -> float:
        """每个 organism 能分到的理论需求"""
        if not self.organisms:
            return self.total_demand
        # 随着竞争者增多，需求非线性递减
        return self.total_demand / (len(self.organisms) ** 0.7)


@dataclass
class CompetitionEngine:
    """管理跨 niche 的竞争动力学

    核心规则：
    1. 同 niche 内 organism 越多，每个分到的下载量越少
    2. 价格低于 niche 均价的 organism 获得更多用户
    3. 评分高的 organism 从评分低的抢用户
    4. niche 过于拥挤时，最弱的被加速淘汰
    """

    niches: dict[str, MarketNiche] = field(default_factory=dict)

    def _niche_key(self, category: str, product_type: str) -> str:
        return f"{product_type}::{category}"

    def _val(self, v) -> str:
        """安全获取枚举/对象的值"""
        return v.value if hasattr(v, 'value') else str(v)

    def register(self, organism) -> MarketNiche:
        """将一个 organism 注册到它的 niche"""
        cat = self._val(getattr(organism.genome, 'category', 'unknown'))
        ptype = self._val(getattr(organism.genome, 'product_type', 'unknown'))
        key = self._niche_key(cat, ptype)

        if key not in self.niches:
            self.niches[key] = MarketNiche(category=cat, product_type=ptype)

        niche = self.niches[key]
        if organism.organism_id not in niche.organisms:
            niche.organisms.append(organism.organism_id)

        # 更新饱和度
        niche.saturation = min(1.0, len(niche.organisms) / 8)

        return niche

    def unregister(self, organism):
        """organism 死亡时移出 niche"""
        cat = self._val(getattr(organism.genome, 'category', 'unknown'))
        ptype = self._val(getattr(organism.genome, 'product_type', 'unknown'))
        key = self._niche_key(cat, ptype)

        if key in self.niches:
            niche = self.niches[key]
            if organism.organism_id in niche.organisms:
                niche.organisms.remove(organism.organism_id)
            niche.saturation = min(1.0, len(niche.organisms) / 8)

    def compete_tick(self, organism, base_income: float,
                     base_downloads: int) -> tuple[float, int]:
        """根据竞争状况调整 organism 的当日收入/下载量"""
        cat = self._val(getattr(organism.genome, 'category', 'unknown'))
        ptype = self._val(getattr(organism.genome, 'product_type', 'unknown'))
        key = self._niche_key(cat, ptype)

        if key not in self.niches:
            return base_income, base_downloads

        niche = self.niches[key]
        competitors = len(niche.organisms)

        if competitors <= 1:
            return base_income, base_downloads

        # ── 竞争调整 ──

        # 1. 拥挤惩罚：同 niche 超过 3 个，每人拿到的基础份额下降
        crowd_factor = 1.0 / (competitors ** 0.5)
        adjusted_income = base_income * crowd_factor
        adjusted_downloads = max(1, int(base_downloads * crowd_factor))

        # 2. 价格优势：价格低的 organism 抢到更多用户
        org_price = getattr(organism.genome, 'price_point', 5.0)
        avg_price = niche.price_index
        if avg_price > 0 and org_price < avg_price:
            price_bonus = 1.0 + (avg_price - org_price) / avg_price * 0.5
            adjusted_income *= price_bonus
            adjusted_downloads = max(1, int(adjusted_downloads * price_bonus))

        # 3. 质量优势：评分高的从低的抢用户
        org_rating = getattr(organism, 'current_rating', 0)
        if org_rating > 3.5 and competitors >= 3:
            quality_bonus = 1.0 + (org_rating - 3.0) * 0.1
            adjusted_income *= quality_bonus
            adjusted_downloads = max(1, int(adjusted_downloads * quality_bonus))

        # 4. 新进入者劣势：新 organism (< 7 天) 需要时间建立口碑
        if getattr(organism, 'days_alive', 0) < 7 and competitors >= 4:
            newbie_penalty = 0.7
            adjusted_income *= newbie_penalty
            adjusted_downloads = max(1, int(adjusted_downloads * newbie_penalty))

        # 5. 更新 niche 价格指数
        alpha = 0.3
        niche.price_index = (1 - alpha) * niche.price_index + alpha * org_price

        return round(adjusted_income, 2), adjusted_downloads

    def accelerate_death(self, organism) -> bool:
        """检查是否应因竞争压力加速死亡"""
        cat = self._val(getattr(organism.genome, 'category', 'unknown'))
        ptype = self._val(getattr(organism.genome, 'product_type', 'unknown'))
        key = self._niche_key(cat, ptype)

        if key not in self.niches:
            return False

        niche = self.niches[key]

        # 如果 niche 饱和度高，且 organism 处于底部 20%
        if niche.saturation > 0.7 and getattr(organism, 'energy', 0) < 1.0:
            # 有 30% 概率被市场直接淘汰
            return random.random() < 0.3

        return False

    @property
    def hottest_niches(self) -> list[MarketNiche]:
        """最拥挤的 niche"""
        return sorted(self.niches.values(),
                     key=lambda n: n.saturation, reverse=True)[:5]

    @property
    def empty_niches(self) -> list[MarketNiche]:
        """还有空间的 niche"""
        return [n for n in self.niches.values()
                if n.saturation < 0.3 and n.competitor_count < 2]

    @property
    def summary(self) -> dict:
        return {
            "total_niches": len(self.niches),
            "hottest": [f"{n.product_type}/{n.category} ({n.competitor_count} orgs)"
                       for n in self.hottest_niches[:3]],
            "available": [f"{n.product_type}/{n.category}"
                         for n in self.empty_niches[:3]],
            "total_organisms_competing": sum(n.competitor_count for n in self.niches.values()),
            "avg_saturation": round(
                sum(n.saturation for n in self.niches.values()) / max(1, len(self.niches)), 2
            ),
        }
