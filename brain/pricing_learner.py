"""自动定价学习引擎

ε-greedy 多臂老虎机：每个品类探索最优定价。
不是瞎猜价格，而是用真实转化数据驱动。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class PriceArm:
    """一个价格实验臂"""
    price_point: float
    impressions: int = 0
    purchases: int = 0
    revenue_cents: int = 0
    last_tested_at: str = ""

    @property
    def conversion_rate(self) -> float:
        if self.impressions == 0:
            return 0.0
        return self.purchases / self.impressions

    @property
    def avg_revenue_per_impression(self) -> float:
        if self.impressions == 0:
            return 0.0
        return (self.revenue_cents / 100) / self.impressions


@dataclass
class CategoryPricing:
    """一个品类的定价实验"""
    category: str
    arms: dict[float, PriceArm] = field(default_factory=dict)
    best_price: float = 4.99
    explore_count: int = 0
    exploit_count: int = 0

    def get_arm(self, price: float) -> PriceArm:
        key = round(price, 2)
        if key not in self.arms:
            self.arms[key] = PriceArm(price_point=key)
        return self.arms[key]

    @property
    def best_arm(self) -> PriceArm | None:
        if not self.arms:
            return None
        return max(self.arms.values(), key=lambda a: a.avg_revenue_per_impression)


class PricingLearner:
    """ε-greedy 定价优化器"""

    def __init__(self, epsilon: float = 0.15):
        self._epsilon = epsilon
        self._cache_path = config.data_dir / "pricing_experiments.json"
        self._categories: dict[str, CategoryPricing] = {}
        self._load()

    def suggest_price(self, category: str, default: float = 4.99) -> float:
        """为一个新产品建议最优价格"""
        cat_key = self._normalize(category)
        if cat_key not in self._categories:
            self._categories[cat_key] = CategoryPricing(category=cat_key)

        cat = self._categories[cat_key]

        # ε-greedy: 探索 vs 剥削
        if random.random() < self._epsilon:
            cat.explore_count += 1
            # 在默认价格附近探索 ±40%
            variation = random.uniform(0.6, 1.4)
            price = round(default * variation, 2)
            return max(0.99, price)

        cat.exploit_count += 1
        best = cat.best_arm
        if best and best.conversion_rate > 0:
            return best.price_point
        return default

    def record_impression(self, category: str, price: float):
        """记录一次产品展示"""
        cat = self._get_or_create(category)
        arm = cat.get_arm(price)
        arm.impressions += 1
        arm.last_tested_at = datetime.now(timezone.utc).isoformat()
        self._save()

    def record_purchase(self, category: str, price: float, revenue_cents: int = 0):
        """记录一次购买"""
        cat = self._get_or_create(category)
        arm = cat.get_arm(price)
        arm.purchases += 1
        if revenue_cents > 0:
            arm.revenue_cents += revenue_cents
        else:
            arm.revenue_cents += int(price * 100)
        self._save()

    def get_category_stats(self, category: str) -> dict:
        """获取品类定价统计"""
        cat = self._get_or_create(category)
        arms_data = {}
        for price, arm in cat.arms.items():
            if arm.impressions > 0:
                arms_data[str(price)] = {
                    "impressions": arm.impressions,
                    "purchases": arm.purchases,
                    "conversion": round(arm.conversion_rate, 4),
                    "arpu": round(arm.avg_revenue_per_impression, 4),
                }
        return {
            "category": cat.category,
            "best_price": cat.best_price,
            "explore": cat.explore_count,
            "exploit": cat.exploit_count,
            "arms": arms_data,
        }

    def update_best_prices(self):
        """根据数据更新每个品类的最优定价"""
        for cat in self._categories.values():
            best = cat.best_arm
            if best and best.impressions >= 3:
                cat.best_price = best.price_point
        self._save()

    def nudge_genome_price(self, genome, category: str) -> float | None:
        """微调基因价格，如果数据支持的话。返回新价格或 None"""
        cat = self._get_or_create(category)
        best = cat.best_arm
        if best and best.impressions >= 5 and best.conversion_rate > 0:
            current = getattr(genome, 'price_point', None)
            if current is None:
                return best.price_point
            # 渐进式向最优价靠拢
            return round(current * 0.7 + best.price_point * 0.3, 2)
        return None

    @property
    def summary(self) -> dict:
        return {
            "categories_tracked": len(self._categories),
            "total_impressions": sum(
                sum(a.impressions for a in c.arms.values())
                for c in self._categories.values()
            ),
            "total_purchases": sum(
                sum(a.purchases for a in c.arms.values())
                for c in self._categories.values()
            ),
            "best_prices": {
                cat: c.best_price for cat, c in self._categories.items()
                if c.best_arm and c.best_arm.impressions >= 3
            },
        }

    def _get_or_create(self, category: str) -> CategoryPricing:
        key = self._normalize(category)
        if key not in self._categories:
            self._categories[key] = CategoryPricing(category=key)
        return self._categories[key]

    @staticmethod
    def _normalize(cat: str) -> str:
        return str(getattr(cat, 'value', cat)).lower().replace(" ", "_")[:40]

    def _save(self):
        try:
            data = {}
            for cat_key, cat in self._categories.items():
                arms = {}
                for price, arm in cat.arms.items():
                    arms[str(price)] = {
                        "price_point": arm.price_point,
                        "impressions": arm.impressions,
                        "purchases": arm.purchases,
                        "revenue_cents": arm.revenue_cents,
                        "last_tested_at": arm.last_tested_at,
                    }
                data[cat_key] = {
                    "category": cat.category,
                    "best_price": cat.best_price,
                    "explore_count": cat.explore_count,
                    "exploit_count": cat.exploit_count,
                    "arms": arms,
                }
            self._cache_path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _load(self):
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text())
                for cat_key, cat_data in data.items():
                    cat = CategoryPricing(
                        category=cat_data.get("category", cat_key),
                        best_price=cat_data.get("best_price", 4.99),
                        explore_count=cat_data.get("explore_count", 0),
                        exploit_count=cat_data.get("exploit_count", 0),
                    )
                    for price_str, arm_data in cat_data.get("arms", {}).items():
                        price = float(price_str)
                        cat.arms[price] = PriceArm(
                            price_point=arm_data["price_point"],
                            impressions=arm_data.get("impressions", 0),
                            purchases=arm_data.get("purchases", 0),
                            revenue_cents=arm_data.get("revenue_cents", 0),
                            last_tested_at=arm_data.get("last_tested_at", ""),
                        )
                    self._categories[cat_key] = cat
            except (json.JSONDecodeError, OSError, KeyError):
                pass
