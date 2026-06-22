"""AlphaX Monitor — 市场监控

每日轮询已部署产品的销售数据。
优先用 Gumroad API，fallback 模拟数据（用于未上架产品）。

监控结果直接喂给 Hive.tick_all() 做每日心跳。
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import urllib.request
import urllib.error

from config import config


@dataclass
class ProductSnapshot:
    organism_id: str
    product_name: str
    gumroad_id: str
    income: float         # 当日收入
    downloads: int        # 当日下载
    rating: float | None  # 当前评分
    cost: float           # 当日 API 消耗


@dataclass
class MarketMonitor:
    """市场数据采集器"""

    snapshots: list[ProductSnapshot] = field(default_factory=list)
    last_run: str = ""

    def poll(self, organisms: dict) -> dict[str, dict]:
        """轮询所有已部署个体，返回 tick 数据"""
        results = {}
        for oid, org in organisms.items():
            if not org.is_alive or not org.gumroad_product_id:
                # 未上架或用模拟
                results[oid] = self._simulate_tick(org)
            else:
                results[oid] = self._poll_gumroad(org)

        self.last_run = datetime.now(timezone.utc).isoformat()
        return results

    def _poll_gumroad(self, org) -> dict:
        """从 Gumroad API 拉取真实销售数据"""
        if not config.gumroad_access_token:
            return self._simulate_tick(org)

        try:
            req = urllib.request.Request(
                f"https://api.gumroad.com/v2/products/{org.gumroad_product_id}",
                headers={"Authorization": f"Bearer {config.gumroad_access_token}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            product = data.get("product", {})
            sales = product.get("sales_count", 0)
            price = product.get("price", 0) / 100  # Gumroad 用分

            return {
                "income": sales * price,
                "downloads": sales,
                "rating": org.current_rating,
                "api_cost": config.daily_burn_rate,
            }
        except (urllib.error.URLError, json.JSONDecodeError, OSError):
            return self._simulate_tick(org)

    def _simulate_tick(self, org) -> dict:
        """市场模拟——基于基因组质量估算表现"""
        if not org.genome:
            return {"income": 0, "downloads": 0, "rating": None, "api_cost": config.daily_burn_rate}

        g = org.genome

        # 基因越"好"，模拟表现越好
        base_downloads = max(0, int(random.gauss(3, 2) * g.survival_rate * 5))

        # 价格影响转化率
        price_factor = max(0.3, 1.0 - (g.price_point - 3.99) / 20)

        downloads = max(0, int(base_downloads * price_factor))
        income = downloads * g.price_point * 0.85  # Gumroad 抽 15%

        # API 消耗：complexity 影响
        cost_map = {"minimal": 0.01, "standard": 0.02, "rich": 0.04}
        api_cost = cost_map.get(g.code_complexity, 0.02)

        return {
            "income": round(income, 2),
            "downloads": downloads,
            "rating": org.current_rating or 4.0,
            "api_cost": api_cost,
        }
