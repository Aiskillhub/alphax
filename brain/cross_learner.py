"""跨产品学习引擎

一个产品卖了 → 分析为什么 → 下一代学会。
不是独立看待每个产品，而是提取"赢家模式"。

赢家信号:
1. 哪些品类高转化
2. 什么价格区间好卖
3. 什么目标受众付费意愿高
4. 什么设计风格被市场验证
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class WinSignal:
    """一条赢家信号"""
    category: str
    product_type: str
    target_audience: str
    design_style: str
    price_point: float
    source: str = ""  # gumroad / internal
    sales_count: int = 1
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class WinningPattern:
    """一个品类的聚合赢家模式"""
    category: str
    sample_count: int = 0
    product_type_scores: dict[str, float] = field(default_factory=dict)
    audience_scores: dict[str, float] = field(default_factory=dict)
    design_scores: dict[str, float] = field(default_factory=dict)
    avg_price: float = 0.0
    total_sales: int = 0


class CrossLearner:
    """跨产品学习：从已卖出的产品提取模式 → 指导新生成"""

    def __init__(self):
        self._cache_path = config.data_dir / "winning_patterns.json"
        self._signals: list[WinSignal] = []
        self._patterns: dict[str, WinningPattern] = {}
        self._load()

    def record_win(self, genome, sales_count: int = 1, source: str = "internal"):
        """记录一个产品的成功"""
        if not genome or sales_count <= 0:
            return

        cat = self._v(getattr(genome, 'category', 'unknown'))
        ptype = self._v(getattr(genome, 'product_type', 'unknown'))
        audience = self._v(getattr(genome, 'target_audience', 'unknown'))
        design = self._v(getattr(genome, 'design_style', 'unknown'))
        price = getattr(genome, 'price_point', 4.99)

        signal = WinSignal(
            category=cat,
            product_type=ptype,
            target_audience=audience,
            design_style=design,
            price_point=float(price) if price else 4.99,
            source=source,
            sales_count=sales_count,
        )
        self._signals.append(signal)
        self._update_patterns(signal)
        self._save()

    def get_genome_biases(self, category: str) -> dict:
        """基于赢家模式返回基因偏向建议"""
        cat_key = self._norm(category)
        pattern = self._patterns.get(cat_key)
        if not pattern or pattern.sample_count < 2:
            return {}

        biases = {}
        if pattern.product_type_scores:
            best_ptype = max(pattern.product_type_scores, key=pattern.product_type_scores.get)
            biases["product_type"] = best_ptype
        if pattern.audience_scores:
            best_aud = max(pattern.audience_scores, key=pattern.audience_scores.get)
            biases["target_audience"] = best_aud
        if pattern.design_scores:
            best_des = max(pattern.design_scores, key=pattern.design_scores.get)
            biases["design_style"] = best_des
        if pattern.avg_price > 0 and pattern.sample_count >= 3:
            biases["price_point"] = round(pattern.avg_price, 2)

        biases["confidence"] = min(1.0, pattern.sample_count / 10)
        return biases

    def get_category_boost(self, category: str) -> float:
        """某品类成功率有多高。1.0=平均，>1=值得多做"""
        cat_key = self._norm(category)
        pattern = self._patterns.get(cat_key)
        if not pattern or pattern.sample_count == 0:
            return 1.0
        # 有销量的品类加分
        return 1.0 + min(0.5, pattern.total_sales * 0.1)

    def top_categories(self, min_samples: int = 1) -> list[tuple[str, float, int]]:
        """最成功的品类排行：(category, boost, sample_count)"""
        ranked = []
        for cat_key, pattern in self._patterns.items():
            if pattern.sample_count >= min_samples and pattern.total_sales > 0:
                scored = pattern.total_sales / max(1, pattern.sample_count)
                ranked.append((pattern.category, scored, pattern.total_sales))
        return sorted(ranked, key=lambda x: x[1], reverse=True)

    @property
    def summary(self) -> dict:
        return {
            "total_signals": len(self._signals),
            "patterns": len(self._patterns),
            "top_categories": [
                {"category": c, "boost": round(b, 2), "sales": s}
                for c, b, s in self.top_categories()[:5]
            ],
        }

    def _update_patterns(self, signal: WinSignal):
        cat_key = self._norm(signal.category)
        if cat_key not in self._patterns:
            self._patterns[cat_key] = WinningPattern(category=signal.category)

        p = self._patterns[cat_key]
        p.sample_count += 1
        p.total_sales += signal.sales_count

        # 指数移动平均更新各类得分
        decay = 0.7
        for field_name, score_attr in [
            ('product_type', 'product_type_scores'),
            ('target_audience', 'audience_scores'),
            ('design_style', 'design_scores'),
        ]:
            val = getattr(signal, field_name, '')
            if not val:
                continue
            scores = getattr(p, score_attr)
            scores[val] = scores.get(val, 0.0) * decay + (1 - decay)

        # 价格移动平均
        if p.avg_price == 0:
            p.avg_price = signal.price_point
        else:
            p.avg_price = p.avg_price * 0.8 + signal.price_point * 0.2

    @staticmethod
    def _v(val) -> str:
        return str(getattr(val, 'value', val))

    @staticmethod
    def _norm(s: str) -> str:
        return CrossLearner._v(s).lower().replace(" ", "_")[:40]

    def _save(self):
        try:
            data = {
                "signals": [
                    {
                        "category": s.category, "product_type": s.product_type,
                        "target_audience": s.target_audience, "design_style": s.design_style,
                        "price_point": s.price_point, "source": s.source,
                        "sales_count": s.sales_count, "detected_at": s.detected_at,
                    }
                    for s in self._signals[-200:]
                ],
                "patterns": {
                    k: {
                        "category": p.category, "sample_count": p.sample_count,
                        "product_type_scores": p.product_type_scores,
                        "audience_scores": p.audience_scores,
                        "design_scores": p.design_scores,
                        "avg_price": p.avg_price, "total_sales": p.total_sales,
                    }
                    for k, p in self._patterns.items()
                },
            }
            self._cache_path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _load(self):
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text())
                for s_data in data.get("signals", []):
                    self._signals.append(WinSignal(**s_data))
                for k, p_data in data.get("patterns", {}).items():
                    self._patterns[k] = WinningPattern(**p_data)
            except (json.JSONDecodeError, OSError, KeyError):
                pass
