"""竞品雷达

持续监控品类下的竞品：谁涨价了、谁上新了、什么在 trending。
不只是自己进化——还要知道市场在往哪里走。
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class CompetitorProduct:
    """一个竞品"""
    product_id: str
    name: str
    price_cents: int
    sales_count: int
    rating: float
    url: str
    category: str = ""
    first_seen: str = ""
    last_updated: str = ""


@dataclass
class MarketSnapshot:
    """某个品类的一次快照"""
    category: str
    total_products: int
    avg_price: float
    price_range: tuple[float, float]
    new_entries: list[str]      # 新增产品名
    price_changes: list[dict]    # 价格变动
    trending_up: list[str]       # 销量上升的
    trending_down: list[str]     # 销量下降的
    scanned_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CompetitorRadar:
    """竞品监控雷达"""

    def __init__(self):
        self._cache_path = config.data_dir / "competitor_radar.json"
        self._snapshots: dict[str, list[MarketSnapshot]] = {}  # category → snapshots
        self._competitors: dict[str, CompetitorProduct] = {}   # product_id → product
        self._token = config.gumroad_access_token
        self._load()

    def scan_category(self, category: str) -> MarketSnapshot:
        """扫描某个品类，返回对比上次的变化"""
        prev = self._get_previous(category)
        products = self._fetch_gumroad_search(category)

        total = len(products)
        prices = [p.get("price_cents", 0) for p in products]
        avg_price = sum(prices) / max(1, len(prices)) / 100

        # 检测新上架
        current_ids = set()
        new_entries = []
        for p in products:
            pid = p.get("id", "")
            current_ids.add(pid)
            if pid not in self._competitors:
                self._competitors[pid] = CompetitorProduct(
                    product_id=pid,
                    name=p.get("name", ""),
                    price_cents=p.get("price_cents", 0),
                    sales_count=p.get("sales_count", 0),
                    rating=p.get("rating", 0),
                    url=p.get("short_url", ""),
                    category=category,
                    first_seen=datetime.now(timezone.utc).isoformat(),
                    last_updated=datetime.now(timezone.utc).isoformat(),
                )
                new_entries.append(p.get("name", ""))

        # 检测价格变动
        price_changes = []
        for pid, cp in self._competitors.items():
            if cp.category != category:
                continue
            # 找当前数据
            current = next((p for p in products if p.get("id") == pid), None)
            if current:
                new_price = current.get("price_cents", 0)
                if new_price != cp.price_cents and cp.price_cents > 0:
                    price_changes.append({
                        "name": cp.name,
                        "old_price": round(cp.price_cents / 100, 2),
                        "new_price": round(new_price / 100, 2),
                    })
                cp.price_cents = new_price
                cp.sales_count = current.get("sales_count", cp.sales_count)
                cp.rating = current.get("rating", cp.rating)
                cp.last_updated = datetime.now(timezone.utc).isoformat()

        # 销量趋势
        trending_up = []
        trending_down = []
        if prev:
            prev_products = {p["name"]: p for p in prev.get("products", [])}
            for p in products:
                name = p.get("name", "")
                if name in prev_products:
                    old_sales = prev_products[name].get("sales_count", 0)
                    new_sales = p.get("sales_count", 0)
                    if new_sales > old_sales + 2:
                        trending_up.append(name)
                    elif new_sales < old_sales:
                        trending_down.append(name)

        snapshot = MarketSnapshot(
            category=category,
            total_products=total,
            avg_price=round(avg_price, 2),
            price_range=(
                round(min(prices) / 100, 2) if prices else 0,
                round(max(prices) / 100, 2) if prices else 0,
            ),
            new_entries=new_entries,
            price_changes=price_changes,
            trending_up=trending_up,
            trending_down=trending_down,
        )

        if category not in self._snapshots:
            self._snapshots[category] = []
        self._snapshots[category].append(snapshot)
        self._save()
        return snapshot

    def get_market_gap(self, category: str) -> dict:
        """分析市场空白：哪里竞争薄弱"""
        snapshots = self._snapshots.get(category, [])
        if not snapshots:
            return {"category": category, "gap_score": 0.8, "reason": "新品类，无竞争数据"}

        latest = snapshots[-1]
        competitors = [
            cp for cp in self._competitors.values()
            if cp.category == category
        ]

        # 竞争少 = 机会大
        if len(competitors) <= 3:
            return {"category": category, "gap_score": 0.8, "reason": f"仅 {len(competitors)} 个竞品"}
        elif len(competitors) <= 10:
            return {"category": category, "gap_score": 0.5, "reason": f"{len(competitors)} 个竞品，中等竞争"}
        else:
            return {"category": category, "gap_score": 0.2, "reason": f"{len(competitors)} 个竞品，红海"}

    def get_alert(self, category: str) -> list[str]:
        """品类动态提醒"""
        alerts = []
        snapshots = self._snapshots.get(category, [])
        if len(snapshots) < 2:
            return alerts

        prev = snapshots[-2]
        curr = snapshots[-1]

        if curr.new_entries:
            alerts.append(f"新品入局: {', '.join(curr.new_entries[:3])}")

        for pc in curr.price_changes:
            direction = "涨" if pc["new_price"] > pc["old_price"] else "降"
            alerts.append(f"{pc['name']} {direction}价 ${pc['old_price']}→${pc['new_price']}")

        if curr.trending_up:
            alerts.append(f"热卖: {', '.join(curr.trending_up[:3])}")

        return alerts

    def _get_previous(self, category: str) -> dict | None:
        snapshots = self._snapshots.get(category, [])
        if not snapshots:
            return None
        return {"products": [
            {"name": cp.name, "sales_count": cp.sales_count, "price_cents": cp.price_cents}
            for cp in self._competitors.values() if cp.category == category
        ]}

    def _fetch_gumroad_search(self, category: str) -> list[dict]:
        """从Gumroad API搜品类产品"""
        if not self._token:
            return []
        try:
            req = urllib.request.Request(
                "https://api.gumroad.com/v2/products",
                headers={"Authorization": f"Bearer {self._token}"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                all_products = data.get("products", [])
                # 简单关键词过滤
                cat_lower = category.lower().replace("_", " ")
                matching = [
                    p for p in all_products
                    if cat_lower in (p.get("name", "") + p.get("description", "")).lower()
                ]
                return matching or all_products[:10]
        except Exception:
            return []

    @property
    def summary(self) -> dict:
        categories = list(self._snapshots.keys())
        return {
            "categories_monitored": len(categories),
            "total_competitors": len(self._competitors),
            "latest_alerts": sum(len(self.get_alert(c)) for c in categories),
            "monitored_categories": categories[:5],
        }

    def _save(self):
        try:
            data = {
                "snapshots": {
                    cat: [
                        {
                            "category": s.category, "total_products": s.total_products,
                            "avg_price": s.avg_price,
                            "price_range": list(s.price_range),
                            "new_entries": s.new_entries,
                            "price_changes": s.price_changes,
                            "trending_up": s.trending_up,
                            "trending_down": s.trending_down,
                            "scanned_at": s.scanned_at,
                        }
                        for s in snap_list[-20:]
                    ]
                    for cat, snap_list in self._snapshots.items()
                },
                "competitors": {
                    pid: {
                        "product_id": cp.product_id, "name": cp.name,
                        "price_cents": cp.price_cents, "sales_count": cp.sales_count,
                        "rating": cp.rating, "url": cp.url, "category": cp.category,
                        "first_seen": cp.first_seen, "last_updated": cp.last_updated,
                    }
                    for pid, cp in self._competitors.items()
                },
            }
            self._cache_path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _load(self):
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text())
                for cat, snap_list in data.get("snapshots", {}).items():
                    self._snapshots[cat] = [MarketSnapshot(**s) for s in snap_list]
                for pid, cp_data in data.get("competitors", {}).items():
                    self._competitors[pid] = CompetitorProduct(**cp_data)
            except (json.JSONDecodeError, OSError, KeyError):
                pass
