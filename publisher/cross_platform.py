"""AlphaX Publisher — 跨平台套利引擎

自动将产品分发到多个 marketplace，动态定价，引流到自建站。

策略：
  - 高抽成平台（Gumroad 10%）：定价高 15-20%，标注"Also available on AlphaX Store"
  - 低抽成平台（Payhip/Lemon Squeezy）：定价略高 5%，测试市场
  - 自建站（0%）：最低价，吸引回头客

支持的平台：
  - Gumroad、Payhip、Lemon Squeezy、自建 Store
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from config import config


# ── 平台配置 ──

@dataclass
class PlatformConfig:
    name: str
    fee_rate: float           # 平台抽成比例
    fixed_fee: float = 0.0    # 固定费用 per transaction
    mor: bool = False         # Merchant of Record（代处理税务）
    api_base: str = ""
    pricing_multiplier: float = 1.0  # 相对自建站的价格倍数

    @property
    def effective_rate(self) -> float:
        """实际到手比例"""
        return 1.0 - self.fee_rate


PLATFORMS = {
    "self_hosted": PlatformConfig(
        name="AlphaX Store",
        fee_rate=0.0,
        pricing_multiplier=1.0,
    ),
    "payhip": PlatformConfig(
        name="Payhip",
        fee_rate=0.05,
        api_base="https://api.payhip.com/v1",
        pricing_multiplier=1.05,
    ),
    "lemon_squeezy": PlatformConfig(
        name="Lemon Squeezy",
        fee_rate=0.05,
        fixed_fee=0.50,
        mor=True,
        api_base="https://api.lemonsqueezy.com/v1",
        pricing_multiplier=1.08,
    ),
    "gumroad": PlatformConfig(
        name="Gumroad",
        fee_rate=0.10,
        fixed_fee=0.50,
        mor=True,
        api_base="https://api.gumroad.com/v2",
        pricing_multiplier=1.15,
    ),
    "polar": PlatformConfig(
        name="Polar",
        fee_rate=0.04,
        fixed_fee=0.40,
        mor=True,
        api_base="https://api.polar.sh/v1",
        pricing_multiplier=1.06,
    ),
    "etsy": PlatformConfig(
        name="Etsy",
        fee_rate=0.065,
        fixed_fee=0.20,
        api_base="https://openapi.etsy.com/v3",
        pricing_multiplier=1.12,
    ),
}


@dataclass
class Listing:
    platform: str
    product_id: str
    title: str
    price: float          # 平台专属价格
    base_price: float     # 自建站价格
    description: str
    tags: list[str]
    listed_at: str = ""
    url: str = ""
    status: str = "draft"  # draft / listed / sold / delisted


@dataclass
class ArbitrageOpportunity:
    """跨平台套利机会"""
    product_id: str
    product_name: str
    strategy: str
    source_platform: str
    target_platform: str
    source_price: float
    target_price: float
    profit_margin: float
    reason: str


class CrossPlatformEngine:
    """跨平台发布 & 套利引擎"""

    def __init__(self, storefront_url: str = ""):
        self.storefront_url = storefront_url or f"http://localhost:8085"
        self.listings: dict[str, dict[str, Listing]] = {}  # product_id -> {platform: Listing}
        self.data_file = config.data_dir / "cross_platform.json"
        self._load()

    def _load(self):
        if self.data_file.exists():
            data = json.loads(self.data_file.read_text())
            for pid, platforms in data.items():
                self.listings[pid] = {}
                for plat, d in platforms.items():
                    self.listings[pid][plat] = Listing(**d)

    def save(self):
        data = {}
        for pid, platforms in self.listings.items():
            data[pid] = {p: vars(l) for p, l in platforms.items()}
        self.data_file.write_text(json.dumps(data, indent=2))

    # ── 智能定价 ──

    def calculate_prices(self, base_price: float) -> dict[str, float]:
        """给定自建站价格，计算各平台最优定价"""
        prices = {}
        for plat_id, plat in PLATFORMS.items():
            platform_price = round(base_price * plat.pricing_multiplier, 2)
            # 确保去掉平台费后到手不低于自建站价格
            net = platform_price * plat.effective_rate - plat.fixed_fee
            if net < base_price * 0.85:  # 到手不得低于 85%
                platform_price = round(
                    (base_price * 0.85 + plat.fixed_fee) / plat.effective_rate, 2)
            prices[plat_id] = platform_price
        return prices

    def optimal_net(self, sale_price: float, platform_id: str) -> float:
        """计算在某个平台实际到手金额"""
        plat = PLATFORMS.get(platform_id)
        if not plat:
            return sale_price
        return round(sale_price * plat.effective_rate - plat.fixed_fee, 2)

    # ── 多平台发布 ──

    def list_product(self, product_id: str, name: str, description: str,
                     base_price: float, tags: list[str] | None = None,
                     platforms: list[str] | None = None) -> dict[str, Listing]:
        """将一个产品发布到多个平台"""
        if platforms is None:
            platforms = ["self_hosted", "payhip", "lemon_squeezy", "gumroad"]

        tags = tags or []
        prices = self.calculate_prices(base_price)
        self.listings[product_id] = {}

        results = {}
        for plat_id in platforms:
            if plat_id not in PLATFORMS:
                continue

            plat = PLATFORMS[plat_id]
            listing = Listing(
                platform=plat_id,
                product_id=product_id,
                title=name,
                price=prices[plat_id],
                base_price=base_price,
                description=self._enrich_description(description, plat_id),
                tags=tags,
                listed_at=datetime.now(timezone.utc).isoformat(),
                status="listed",
            )

            # 自建站直接标记
            if plat_id == "self_hosted":
                listing.url = f"{self.storefront_url}/buy/{product_id}"
                try:
                    from publisher.storefront import add_to_store
                    add_to_store(product_id, name, description, base_price)
                except ImportError:
                    pass

            self.listings[product_id][plat_id] = listing
            results[plat_id] = listing

        self.save()
        return results

    def _enrich_description(self, description: str, platform_id: str) -> str:
        """根据平台优化描述"""
        if platform_id == "self_hosted":
            return description
        # 第三方平台：添加引流
        return (
            f"{description}\n\n---\n"
            f"Also available at a lower price on AlphaX Store: "
            f"{self.storefront_url}"
        )

    # ── 套利发现 ──

    def find_arbitrage_opportunities(self) -> list[ArbitrageOpportunity]:
        """发现跨平台套利机会"""
        opportunities = []

        for pid, platforms in self.listings.items():
            listed = {p: l for p, l in platforms.items() if l.status == "listed"}
            if len(listed) < 2:
                continue

            for p1, l1 in listed.items():
                for p2, l2 in listed.items():
                    if p1 >= p2:
                        continue

                    price_diff_pct = (l1.price - l2.price) / l2.price
                    net1 = self.optimal_net(l1.price, p1)
                    net2 = self.optimal_net(l2.price, p2)

                    # 套利：在低价平台买，在高价平台卖
                    if price_diff_pct > 0.15 and net2 > net1 * 1.1:
                        opportunities.append(ArbitrageOpportunity(
                            product_id=pid,
                            product_name=l1.title,
                            strategy="price_arbitrage",
                            source_platform=p2,  # 便宜平台
                            target_platform=p1,  # 贵平台
                            source_price=l2.price,
                            target_price=l1.price,
                            profit_margin=round(price_diff_pct, 3),
                            reason=f"${l2.price} on {p2} vs ${l1.price} on {p1} "
                                   f"({price_diff_pct:.0%} spread)",
                        ))

        return opportunities

    # ── 渠道优化 ──

    def best_channel(self, product_id: str) -> str:
        """返回利润最高的销售渠道"""
        if product_id not in self.listings:
            return "self_hosted"

        best = ("self_hosted", 1.0)
        for plat_id, listing in self.listings[product_id].items():
            net_pct = self.optimal_net(listing.price, plat_id) / listing.price
            if net_pct > best[1]:
                best = (plat_id, net_pct)
        return best[0]

    def channel_recommendation(self, genome) -> dict:
        """根据基因组推荐最佳渠道组合"""
        rec = {"primary": "self_hosted", "secondary": [], "skip": []}

        if genome.price_point < 5:
            rec["secondary"] = ["payhip", "polar"]
            rec["skip"] = ["gumroad"]  # 低价商品，Gumroad 固定费太贵
        elif genome.price_point < 20:
            rec["secondary"] = ["payhip", "lemon_squeezy", "gumroad"]
        else:
            rec["secondary"] = ["lemon_squeezy", "gumroad", "payhip"]

        if genome.target_market.value == "developer":
            rec["secondary"].append("polar")  # 开发者喜欢 Polar

        return rec

    # ── 报告 ──

    def report(self) -> str:
        total_products = len(self.listings)
        total_listings = sum(len(p) for p in self.listings.values())
        opps = self.find_arbitrage_opportunities()

        lines = [
            f"跨平台引擎: {total_products} 产品, {total_listings} 个 listing",
            f"套利机会: {len(opps)} 个",
        ]
        if opps:
            lines.append("  最佳套利:")
            for o in opps[:3]:
                lines.append(f"    {o.product_name}: {o.reason}")
        return "\n".join(lines)


# ── CLI ──

if __name__ == "__main__":
    engine = CrossPlatformEngine()

    # Demo: list a test product
    results = engine.list_product(
        product_id="demo_product",
        name="AI Prompt Mastery Pack",
        description="Curated collection of 50+ high-quality AI prompts for developers and creators.",
        base_price=14.99,
        tags=["ai", "prompts", "productivity"],
    )

    print("Listed on:")
    for plat, listing in results.items():
        net = engine.optimal_net(listing.price, plat)
        print(f"  {plat}: ${listing.price} → 到手 ${net} ({PLATFORMS[plat].name})")

    opps = engine.find_arbitrage_opportunities()
    if opps:
        print(f"\n套利机会 ({len(opps)}):")
        for o in opps:
            print(f"  {o.reason}")
    else:
        print("\n无套利机会（需要至少 2 个 listing）")
