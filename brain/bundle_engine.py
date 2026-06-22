"""技能组合引擎

不是单品思维——自动发现产品间的互补关系，打包成套装。
"买了 A 的人也买了 B" → 自动捆绑 → 更高客单价。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class ProductEdge:
    """两个产品间的关联"""
    source_id: str
    target_id: str
    strength: float = 0.0  # 0-1, 关联强度
    co_views: int = 0       # 同时被查看次数
    co_purchases: int = 0    # 同时被购买次数
    reason: str = ""         # 为什么关联


@dataclass
class Bundle:
    """一个推荐套装"""
    bundle_id: str
    name: str
    product_ids: list[str]
    total_price: float
    bundle_price: float       # 套装折扣价
    discount_pct: int
    reason: str
    sales_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BundleEngine:
    """自动发现产品组合 → 生成套装推荐"""

    def __init__(self):
        self._edges_path = config.data_dir / "product_edges.json"
        self._bundles_path = config.data_dir / "bundles.json"
        self._edges: dict[str, dict[str, ProductEdge]] = {}
        self._bundles: list[Bundle] = []
        self._view_history: list[dict] = []  # {product_ids, timestamp}
        self._purchase_history: list[dict] = []
        self._load()

    def record_view(self, product_ids: list[str]):
        """记录一次浏览（看了哪些产品）"""
        if len(product_ids) >= 2:
            self._view_history.append({
                "product_ids": product_ids,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            for i, pid_a in enumerate(product_ids):
                for pid_b in product_ids[i + 1:]:
                    self._strengthen_edge(pid_a, pid_b, view=True)
            self._save_edges()

    def record_purchase(self, product_ids: list[str]):
        """记录一次购买"""
        if len(product_ids) >= 2:
            self._purchase_history.append({
                "product_ids": product_ids,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            for i, pid_a in enumerate(product_ids):
                for pid_b in product_ids[i + 1:]:
                    self._strengthen_edge(pid_a, pid_b, purchase=True)
            self._save_edges()

    def suggest_bundles(self, all_products: list[dict], max_bundles: int = 3) -> list[Bundle]:
        """基于关联图生成套装推荐"""
        if not self._edges:
            return []

        # 找强关联的产品对
        pairs = []
        for pid_a, targets in self._edges.items():
            for pid_b, edge in targets.items():
                if edge.strength >= 0.3:
                    pairs.append((pid_a, pid_b, edge))

        pairs.sort(key=lambda x: x[2].strength, reverse=True)

        # 构建套装（贪心：取最强关联对，扩展成团）
        used_ids = set()
        bundles = []

        for pid_a, pid_b, edge in pairs[:10]:
            if pid_a in used_ids or pid_b in used_ids:
                continue

            # 找跟这两个都相关的第三个产品
            related_a = set(self._edges.get(pid_a, {}).keys())
            related_b = set(self._edges.get(pid_b, {}).keys())
            candidates = (related_a & related_b) - {pid_a, pid_b}

            bundle_ids = [pid_a, pid_b]
            for cid in list(candidates)[:2]:
                if cid not in used_ids:
                    bundle_ids.append(cid)
                    used_ids.add(cid)

            used_ids.add(pid_a)
            used_ids.add(pid_b)

            # 计算价格
            products_in = [p for p in all_products if p.get("id") in bundle_ids]
            total = sum(p.get("price_cents", 499) for p in products_in) / 100
            discount = min(30, 10 + len(bundle_ids) * 5)
            bundle_price = round(total * (1 - discount / 100), 2)

            # 命名
            names = [p.get("name", "") for p in products_in[:2]]
            bundle_name = f"{names[0][:20]} + {names[1][:20]} Bundle" if len(names) >= 2 else "Power Bundle"

            bundle = Bundle(
                bundle_id=f"bundle_{len(bundles)}_{int(datetime.now(timezone.utc).timestamp())}",
                name=bundle_name,
                product_ids=bundle_ids,
                total_price=round(total, 2),
                bundle_price=bundle_price,
                discount_pct=discount,
                reason=edge.reason or f"常被一起购买 (关联度 {edge.strength:.0%})",
            )
            bundles.append(bundle)

            if len(bundles) >= max_bundles:
                break

        self._bundles = bundles
        self._save_bundles()
        return bundles

    def get_bundles_for_product(self, product_id: str) -> list[Bundle]:
        """某个产品参与的套装"""
        return [b for b in self._bundles if product_id in b.product_ids]

    def get_related_products(self, product_id: str, limit: int = 5) -> list[dict]:
        """获取关联产品推荐"""
        targets = self._edges.get(product_id, {})
        sorted_edges = sorted(targets.values(), key=lambda e: e.strength, reverse=True)
        return [
            {
                "product_id": e.target_id,
                "strength": round(e.strength, 2),
                "reason": e.reason or f"关联度 {e.strength:.0%}",
            }
            for e in sorted_edges[:limit]
        ]

    def _strengthen_edge(self, pid_a: str, pid_b: str, view: bool = False, purchase: bool = False):
        key_a, key_b = sorted([pid_a, pid_b])

        if key_a not in self._edges:
            self._edges[key_a] = {}
        if key_b not in self._edges[key_a]:
            self._edges[key_a][key_b] = ProductEdge(source_id=key_a, target_id=key_b)

        edge = self._edges[key_a][key_b]
        if view:
            edge.co_views += 1
        if purchase:
            edge.co_purchases += 1

        # 强度 = 购买信号加权 + 浏览信号
        edge.strength = min(1.0, edge.co_purchases * 0.4 + edge.co_views * 0.1)

        if edge.co_purchases > 0:
            edge.reason = f"一起买了 {edge.co_purchases} 次"
        elif edge.co_views > 2:
            edge.reason = f"一起看了 {edge.co_views} 次"

    @property
    def summary(self) -> dict:
        return {
            "edges": sum(len(targets) for targets in self._edges.values()),
            "bundles": len(self._bundles),
            "strongest_edge": max(
                ((e.strength, e.reason) for targets in self._edges.values() for e in targets.values()),
                key=lambda x: x[0], default=(0, "")
            )[0],
            "active_bundles": [b.name for b in self._bundles[-3:]],
        }

    def _save_edges(self):
        try:
            data = {
                f"{src}|{tgt}": {
                    "source_id": e.source_id, "target_id": e.target_id,
                    "strength": e.strength, "co_views": e.co_views,
                    "co_purchases": e.co_purchases, "reason": e.reason,
                }
                for src, targets in self._edges.items()
                for tgt, e in targets.items()
            }
            self._edges_path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _save_bundles(self):
        try:
            data = [
                {
                    "bundle_id": b.bundle_id, "name": b.name,
                    "product_ids": b.product_ids, "total_price": b.total_price,
                    "bundle_price": b.bundle_price, "discount_pct": b.discount_pct,
                    "reason": b.reason, "sales_count": b.sales_count,
                    "created_at": b.created_at,
                }
                for b in self._bundles
            ]
            self._bundles_path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _load(self):
        if self._edges_path.exists():
            try:
                data = json.loads(self._edges_path.read_text())
                for key, e_data in data.items():
                    src, tgt = key.split("|")
                    if src not in self._edges:
                        self._edges[src] = {}
                    self._edges[src][tgt] = ProductEdge(**e_data)
            except (json.JSONDecodeError, OSError, KeyError):
                pass

        if self._bundles_path.exists():
            try:
                data = json.loads(self._bundles_path.read_text())
                self._bundles = [Bundle(**b) for b in data]
            except (json.JSONDecodeError, OSError, KeyError):
                pass
