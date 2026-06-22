"""AlphaX 知识复利引擎

学习分三层：
  Layer 1 基因级: 标记哪些基因组合导致成功/失败
  Layer 2 策略级: 市场状态 → 策略 → 结果 的映射
  Layer 3 元认知: 学会怎么学习（先 MVP 验证、抄差评做差异化等）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from config import config


@dataclass
class KnowledgeEngine:
    """从投放历史中提炼可复用的知识模式"""

    market_insights: dict[str, dict] = field(default_factory=dict)
    strategy_map: list[dict] = field(default_factory=list)
    meta_patterns: list[dict] = field(default_factory=list)

    _path: Path = config.data_dir / "knowledge.json"

    def __post_init__(self):
        if self._path.exists():
            data = json.loads(self._path.read_text())
            self.market_insights = data.get("market_insights", {})
            self.strategy_map = data.get("strategy_map", [])
            self.meta_patterns = data.get("meta_patterns", [])

    # ── 策略匹配 ──

    def best_strategy_for(self, category: str, competition_level: str) -> dict | None:
        """给定品类和竞争水平，返回历史最佳策略"""
        candidates = [
            s for s in self.strategy_map
            if s["category"] == category
            and s.get("competition") == competition_level
            and s["result"]["survived"]
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda s: s["result"]["net_profit"], reverse=True)
        best = candidates[0]
        return {
            "price_point": best["price_point"],
            "pricing_model": best["pricing_model"],
            "target_market": best["target_market"],
            "expected_revenue": best["result"]["net_profit"],
            "survival_rate": best["result"].get("survival_rate", 0.5),
            "sample_size": len(candidates),
        }

    # ── 品类分析 ──

    def category_health(self, category: str) -> dict:
        """分析一个品类的市场健康度"""
        entries = [s for s in self.strategy_map if s["category"] == category]
        if not entries:
            return {"status": "unknown", "samples": 0}

        survived = [s for s in entries if s["result"]["survived"]]
        return {
            "status": "hot" if len(survived) / len(entries) > 0.5 else "cold",
            "samples": len(entries),
            "survival_rate": len(survived) / len(entries),
            "avg_net_profit": (
                sum(s["result"]["net_profit"] for s in survived) / len(survived)
                if survived else 0
            ),
            "competition_density": len(entries),  # 同一品类有多少尝试
        }

    # ── 学习 ──

    def learn_from_result(
        self,
        category: str,
        price_point: float,
        pricing_model: str,
        target_market: str,
        competition: str,
        result: dict,
    ):
        """从一次投放结果中学习"""
        self.strategy_map.append({
            "category": category,
            "price_point": price_point,
            "pricing_model": pricing_model,
            "target_market": target_market,
            "competition": competition,
            "result": result,
        })

        # 更新品类洞察
        if category not in self.market_insights:
            self.market_insights[category] = {"total": 0, "survived": 0}
        self.market_insights[category]["total"] += 1
        if result["survived"]:
            self.market_insights[category]["survived"] += 1

        self._discover_meta_patterns()
        self.save()

    def _discover_meta_patterns(self):
        """从积累的数据中自动发现元模式"""
        if len(self.strategy_map) < 20:
            return

        # 模式 1：价格与存活率的关系
        low_price = [s for s in self.strategy_map if s["price_point"] <= 4.99]
        high_price = [s for s in self.strategy_map if s["price_point"] >= 9.99]
        if low_price and high_price:
            low_survival = sum(1 for s in low_price if s["result"]["survived"]) / len(low_price)
            high_survival = sum(1 for s in high_price if s["result"]["survived"]) / len(high_price)
            if low_survival > high_survival * 1.5:
                self._upsert_pattern(
                    "pricing",
                    "低价策略存活率显著高于高价策略",
                    f"${low_price[0]['price_point']}级存活率{low_survival:.0%} vs ${high_price[0]['price_point']}级{high_survival:.0%}",
                    min(low_survival, 0.9),
                )

        # 模式 2：品类与利润的关系
        for cat in set(s["category"] for s in self.strategy_map):
            cat_entries = [s for s in self.strategy_map if s["category"] == cat]
            if len(cat_entries) >= 5:
                profits = [s["result"]["net_profit"] for s in cat_entries if s["result"]["survived"]]
                if profits and sum(profits) / len(profits) > 100:
                    self._upsert_pattern(
                        "category",
                        f"品类 {cat} 盈利能力强",
                        f"平均净利润 ${sum(profits)/len(profits):.0f}",
                        0.7,
                    )

    def _upsert_pattern(self, tag: str, title: str, detail: str, confidence: float):
        for p in self.meta_patterns:
            if p["title"] == title:
                p["confidence"] = confidence
                return
        self.meta_patterns.append({
            "tag": tag, "title": title, "detail": detail, "confidence": confidence,
        })

    def save(self):
        self._path.write_text(json.dumps({
            "market_insights": self.market_insights,
            "strategy_map": self.strategy_map,
            "meta_patterns": self.meta_patterns,
        }, indent=2))
