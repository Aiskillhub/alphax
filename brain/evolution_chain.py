"""进化链日志

每个产品不是突然出现的——它是一条进化链上的最新节点。
公共可见的进化历史 = 最强营销：买家看到 AI 在学习和改进。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class EvolutionEvent:
    """进化链上的一个事件"""
    event_type: str       # created / deployed / iterated / price_changed / sold / died
    version: int
    description: str
    details: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class EvolutionChain:
    """一个产品的完整进化链"""
    product_id: str
    product_name: str
    category: str = ""
    chain: list[EvolutionEvent] = field(default_factory=list)
    current_version: int = 1
    total_sales: int = 0
    total_revenue: float = 0.0
    days_alive: int = 0
    alive: bool = True
    born_at: str = ""
    showcase_text: str = ""  # 自动生成的展示文案


class EvolutionChainLogger:
    """记录并展示产品的进化历程"""

    def __init__(self):
        self._cache_path = config.data_dir / "evolution_chains.json"
        self._chains: dict[str, EvolutionChain] = {}
        self._load()

    def record_created(self, product_id: str, product_name: str, category: str, genome_data: dict):
        """记录产品诞生"""
        chain = self._get_or_create(product_id, product_name, category)
        chain.born_at = datetime.now(timezone.utc).isoformat()
        chain.chain.append(EvolutionEvent(
            event_type="created",
            version=1,
            description=f"Alpha X 引擎生成: {product_name}",
            details={
                "category": category,
                "initial_price": genome_data.get("price_point", 0),
                "product_type": str(genome_data.get("product_type", "")),
                "target_audience": str(genome_data.get("target_audience", "")),
                "mutation_gen": genome_data.get("generation", 1),
            },
        ))
        self._update_showcase(chain)
        self._save()

    def record_deployed(self, product_id: str, url: str):
        """记录上架事件"""
        chain = self._chains.get(product_id)
        if not chain:
            return
        chain.chain.append(EvolutionEvent(
            event_type="deployed",
            version=chain.current_version,
            description=f"上架到 {url}",
            details={"url": url, "platform": "gumroad" if "gumroad" in url else "unknown"},
        ))
        self._save()

    def record_iteration(self, product_id: str, old_title: str, new_title: str, reason: str):
        """记录产品自我迭代"""
        chain = self._chains.get(product_id)
        if not chain:
            return
        chain.current_version += 1
        chain.chain.append(EvolutionEvent(
            event_type="iterated",
            version=chain.current_version,
            description=f"自我迭代 v{chain.current_version}: {reason}",
            details={"old_title": old_title, "new_title": new_title, "reason": reason},
        ))
        self._update_showcase(chain)
        self._save()

    def record_price_change(self, product_id: str, old_price: float, new_price: float, reason: str):
        """记录价格变化"""
        chain = self._chains.get(product_id)
        if not chain:
            return
        chain.current_version += 1
        direction = "涨" if new_price > old_price else "降"
        chain.chain.append(EvolutionEvent(
            event_type="price_changed",
            version=chain.current_version,
            description=f"自动调价: ${old_price} → ${new_price} ({direction} {(abs(new_price-old_price)/old_price*100):.0f}%)",
            details={
                "old_price": old_price, "new_price": new_price,
                "reason": reason, "pct_change": round((new_price - old_price) / old_price * 100),
            },
        ))
        self._update_showcase(chain)
        self._save()

    def record_sale(self, product_id: str, revenue: float):
        """记录一次销售"""
        chain = self._chains.get(product_id)
        if not chain:
            return
        chain.total_sales += 1
        chain.total_revenue += revenue
        chain.chain.append(EvolutionEvent(
            event_type="sold",
            version=chain.current_version,
            description=f"售出 #{chain.total_sales} — +${revenue:.2f}",
            details={"revenue": revenue, "total_sales": chain.total_sales},
        ))
        if chain.total_sales == 1:
            # 第一单！加特殊标记
            chain.chain[-1].description += " 🎉 首单！"
        elif chain.total_sales >= 10:
            chain.chain[-1].description += " 🔥 热卖中！"
        self._update_showcase(chain)
        self._save()

    def record_death(self, product_id: str, reason: str):
        """记录产品下架/死亡"""
        chain = self._chains.get(product_id)
        if not chain:
            return
        chain.alive = False
        chain.chain.append(EvolutionEvent(
            event_type="died",
            version=chain.current_version,
            description=f"产品下架: {reason}",
            details={"total_sales": chain.total_sales, "total_revenue": chain.total_revenue},
        ))
        self._update_showcase(chain)
        self._save()

    def get_chain(self, product_id: str) -> EvolutionChain | None:
        return self._chains.get(product_id)

    def get_showcase(self, product_id: str) -> dict:
        """获取产品的进化展示数据（用于产品页面）"""
        chain = self._chains.get(product_id)
        if not chain:
            return {"has_chain": False, "message": "无进化记录"}

        # 选取关键事件
        key_events = []
        for evt in chain.chain:
            if evt.event_type in ("created", "iterated", "price_changed", "sold"):
                key_events.append({
                    "version": f"v{evt.version}",
                    "type": evt.event_type,
                    "description": evt.description,
                    "when": evt.timestamp[:10],
                })

        # 里程碑
        milestones = []
        if chain.days_alive >= 7:
            milestones.append("存活 7 天")
        if chain.total_sales >= 1:
            milestones.append(f"首单达成")
        if chain.total_sales >= 5:
            milestones.append(f"5 单达成")
        if chain.total_revenue >= 50:
            milestones.append(f"收入 $50+")
        if chain.current_version >= 3:
            milestones.append(f"自我迭代 {chain.current_version} 次")

        return {
            "has_chain": True,
            "product_name": chain.product_name,
            "category": chain.category,
            "current_version": chain.current_version,
            "total_sales": chain.total_sales,
            "total_revenue": round(chain.total_revenue, 2),
            "days_alive": chain.days_alive,
            "alive": chain.alive,
            "key_events": key_events[-8:],
            "milestones": milestones,
            "showcase_text": chain.showcase_text,
            "born_at": chain.born_at[:10] if chain.born_at else "",
        }

    def get_platform_showcase(self) -> list[dict]:
        """平台级别的进化展示：所有产品的进化亮点"""
        result = []
        for pid, chain in sorted(
            self._chains.items(),
            key=lambda x: x[1].total_revenue,
            reverse=True,
        ):
            if chain.total_sales > 0:
                result.append({
                    "product_name": chain.product_name,
                    "total_sales": chain.total_sales,
                    "total_revenue": round(chain.total_revenue, 2),
                    "versions": chain.current_version,
                    "showcase": chain.showcase_text[:150],
                })
        return result[:10]

    def _get_or_create(self, pid: str, name: str, category: str) -> EvolutionChain:
        if pid not in self._chains:
            self._chains[pid] = EvolutionChain(
                product_id=pid, product_name=name, category=category,
            )
        return self._chains[pid]

    def _update_showcase(self, chain: EvolutionChain):
        """自动生成展示文案"""
        parts = [f"{chain.product_name} 由 Alpha X 引擎自动生成"]

        if chain.total_sales == 0 and chain.current_version > 1:
            parts.append(f"经 {chain.current_version} 次自我迭代优化中")
        elif chain.total_sales == 1:
            parts.append("已获得首单验证")
        elif chain.total_sales >= 5:
            parts.append(f"已售出 {chain.total_sales} 份，收入 ${chain.total_revenue:.2f}")
        elif chain.total_sales > 0:
            parts.append(f"已售出 {chain.total_sales} 份")

        # 找最重要的进化事件
        iterations = [e for e in chain.chain if e.event_type == "iterated"]
        price_changes = [e for e in chain.chain if e.event_type == "price_changed"]
        if price_changes:
            last_pc = price_changes[-1]
            parts.append(f"AI 自动调整过 {len(price_changes)} 次定价")
        if iterations:
            parts.append(f"AI 自我改进了 {len(iterations)} 次")

        chain.showcase_text = "。".join(parts) + "。"

    @property
    def summary(self) -> dict:
        alive = [c for c in self._chains.values() if c.alive]
        sold = [c for c in self._chains.values() if c.total_sales > 0]
        return {
            "total_products_tracked": len(self._chains),
            "alive": len(alive),
            "with_sales": len(sold),
            "total_platform_revenue": round(sum(c.total_revenue for c in self._chains.values()), 2),
            "most_evolved": max(
                ((c.product_name, c.current_version) for c in self._chains.values()),
                key=lambda x: x[1], default=("", 0)
            ),
            "top_seller": max(
                ((c.product_name, c.total_sales) for c in self._chains.values()),
                key=lambda x: x[1], default=("", 0)
            ),
        }

    def _save(self):
        try:
            data = {
                pid: {
                    "product_id": c.product_id, "product_name": c.product_name,
                    "category": c.category, "current_version": c.current_version,
                    "total_sales": c.total_sales, "total_revenue": c.total_revenue,
                    "days_alive": c.days_alive, "alive": c.alive,
                    "born_at": c.born_at, "showcase_text": c.showcase_text,
                    "chain": [
                        {
                            "event_type": e.event_type, "version": e.version,
                            "description": e.description, "details": e.details,
                            "timestamp": e.timestamp,
                        }
                        for e in c.chain
                    ],
                }
                for pid, c in self._chains.items()
            }
            self._cache_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        except OSError:
            pass

    def _load(self):
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text())
                for pid, c_data in data.items():
                    chain_data = c_data.pop("chain", [])
                    chain = EvolutionChain(**c_data)
                    chain.chain = [EvolutionEvent(**e) for e in chain_data]
                    self._chains[pid] = chain
            except (json.JSONDecodeError, OSError, KeyError):
                pass
