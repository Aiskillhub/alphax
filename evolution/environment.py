"""环境抽象 + 模拟环境

Environment 是进化引擎里的"世界"。不同环境定义不同的选择压力。
"""

from __future__ import annotations

import json
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from core.genome import Category
from config import config

logger = logging.getLogger("alphax.environment")


@dataclass
class TickResult:
    """环境每天为每个 organism 返回的数据"""
    income: float = 0.0
    downloads: int = 0
    rating: float | None = None
    api_cost: float = 0.02


@dataclass
class DeployResult:
    success: bool
    deployment_id: str = ""
    error: str = ""


@dataclass
class MarketContext:
    category_health: dict[str, dict] = field(default_factory=dict)
    competition_levels: dict[str, str] = field(default_factory=dict)
    trending_categories: list[str] = field(default_factory=list)


class Environment(ABC):
    """可插拔的环境基类。环境是进化的选择者——它决定谁活谁死。"""

    @abstractmethod
    def deploy(self, organism, artifact_path: str) -> DeployResult:
        """将一个 organism 的构建产物部署到环境中"""
        ...

    @abstractmethod
    def tick(self, organism) -> TickResult:
        """每日心跳：返回 organism 当天的表现"""
        ...

    @abstractmethod
    def market_context(self) -> MarketContext:
        """聚合市场数据，供 Gene Pool 决策用"""
        ...


class SimulatedEnvironment(Environment):
    """模拟市场环境。

    基于基因组质量 + 品类热度 + 饱和度惩罚估算表现。
    不是真实市场，但足够让进化闭环跑起来。
    换真实环境时不需要改引擎代码。
    """

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self._deployments: dict[str, str] = {}  # organism_id -> deployment_id
        # 品类热度：某些品类天然需求量更大
        self._category_demand = {
            "ai_chat": 1.4, "dev_tools": 1.2, "productivity": 1.0,
            "automation": 1.1, "content": 0.8, "data": 0.9, "seo": 0.7,
        }

    def deploy(self, organism, artifact_path: str) -> DeployResult:
        oid = organism.organism_id
        self._deployments[oid] = f"dep_{oid[:8]}"
        return DeployResult(success=True, deployment_id=self._deployments[oid])

    def tick(self, organism) -> TickResult:
        genome = organism.genome
        if not genome:
            return TickResult(api_cost=config.daily_burn_rate)

        # 品类需求因子
        demand = self._category_demand.get(genome.category.value, 1.0)

        # 价格影响转化率
        price_factor = max(0.2, 1.0 - (genome.price_point - 2.99) / 25)

        # 饱和度惩罚：同品类 organism 太多 → 单个收入下降
        saturation = self._saturation_penalty(genome.category)

        # 坏日子：10% 概率低下载量，模拟真实市场波动
        bad_day = self.rng.random() < 0.10
        mean_dl = 1 if bad_day else 4
        base = max(0, int(self.rng.gauss(mean_dl, 3) * demand * price_factor * saturation))
        downloads = max(0, base)
        income = round(downloads * genome.price_point * 0.85, 2)

        cost_map = {"minimal": 0.01, "standard": 0.02, "rich": 0.04}
        api_cost = cost_map.get(genome.code_complexity, 0.02)

        rating = organism.current_rating or round(self.rng.uniform(3.5, 5.0), 1)
        return TickResult(income=income, downloads=downloads, rating=rating, api_cost=api_cost)

    def _saturation_penalty(self, category) -> float:
        same_cat = sum(
            1 for oid in self._deployments
            if hasattr(self, '_org_category') and self._org_category.get(oid) == category.value
        )
        return max(0.3, 1.0 - same_cat * 0.05)

    def market_context(self) -> MarketContext:
        health = {}
        for cat in Category:
            d = self._category_demand.get(cat.value, 1.0)
            health[cat.value] = {"survival_rate": 0.4 + d * 0.15, "avg_net_profit": 5 + d * 10, "samples": 10}
        return MarketContext(
            category_health=health,
            competition_levels={c.value: "medium" for c in Category},
            trending_categories=["ai_chat", "dev_tools", "automation"],
        )


class GumroadEnvironment(Environment):
    """真实 Gumroad 市场环境。

    将 organism 的构建产物上传到 Gumroad，每日拉取真实销售数据。
    无 token 时回退模拟。
    """

    def __init__(self, access_token: str = "", seed: int = 42):
        self.access_token = access_token or config.gumroad_access_token
        self._sim = SimulatedEnvironment(seed=seed)
        self._deployments: dict[str, str] = {}  # organism_id -> gumroad_product_id

    def deploy(self, organism, artifact_path: str) -> DeployResult:
        if not self.access_token:
            return self._sim.deploy(organism, artifact_path)

        # 找到构建产物
        import zipfile
        build_dir = Path(artifact_path) if artifact_path else None
        if not build_dir or not build_dir.exists():
            return DeployResult(success=False, error="构建产物不存在")

        # 打包成 zip（Gumroad 格式要求）
        zip_path = build_dir.parent / f"{build_dir.name}.zip"
        if not zip_path.exists():
            return DeployResult(success=False, error="zip 文件不存在")

        # 上传到 Gumroad
        try:
            gid = self._create_gumroad_product(organism, zip_path)
            if gid:
                self._deployments[organism.organism_id] = gid
                return DeployResult(success=True, deployment_id=gid)
        except Exception as e:
            return DeployResult(success=False, error=str(e))

        return DeployResult(success=False, error="上传失败")

    def _create_gumroad_product(self, organism, zip_path: Path) -> str:
        genome = organism.genome
        name = genome.express() if genome else "Digital Tool"

        import urllib.request
        import urllib.error

        body = json.dumps({
            "name": name[:100],
            "description": f"AI 自主进化生成的 {genome.category.value if genome else 'dev'} 工具",
            "price": int((genome.price_point if genome else 4.99) * 100),  # 分
            "published": True,
        }).encode()

        req = urllib.request.Request(
            "https://api.gumroad.com/v2/products",
            data=body,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data.get("product", {}).get("id", "")

    def tick(self, organism) -> TickResult:
        gid = self._deployments.get(organism.organism_id, "")
        if not gid or not self.access_token:
            return self._sim.tick(organism)

        try:
            import urllib.request
            req = urllib.request.Request(
                f"https://api.gumroad.com/v2/products/{gid}",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            product = data.get("product", {})
            sales = product.get("sales_count", 0)
            price = product.get("price", 0) / 100

            return TickResult(
                income=round(sales * price * 0.85, 2),  # Gumroad 抽 15%
                downloads=sales,
                rating=organism.current_rating,
                api_cost=config.daily_burn_rate,
            )
        except Exception as e:
            logger.warning(f"Gumroad tick failed for {organism.organism_id}: {e}")
            return self._sim.tick(organism)

    def sync_all_sales(self) -> dict[str, dict]:
        """拉取所有 Gumroad 产品的真实销售数据，映射回 organism"""
        if not self.access_token:
            return {}
        sales = {}
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://api.gumroad.com/v2/products",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            for p in data.get("products", []):
                pid = p.get("id", "")
                sales[pid] = {
                    "name": p.get("name", ""),
                    "sales_count": p.get("sales_count", 0),
                    "revenue_cents": p.get("revenue", 0),
                    "rating": p.get("average_rating", 0),
                }
            logger.info(f"Gumroad sync: {len(sales)} products with sales data")
        except Exception as e:
            logger.warning(f"Gumroad sync_all_sales failed: {e}")
        return sales

    def market_context(self) -> MarketContext:
        return self._sim.market_context()
