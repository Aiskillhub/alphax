"""Layer 4: 竞标引擎

需求广播 → Agent 竞标 → 供需匹配

流程：
  1. Organism 发现缺少某个能力 → 广播需求到市场
  2. 匹配的 Agent 提交报价（价格 + 预估质量 + 交付时间）
  3. 竞标引擎按最优性价比选胜者
  4. 进入托管结算
"""

from __future__ import annotations

import json
import time
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from config import config
from layer4.service_directory import ServiceDirectory, Capability


@dataclass
class Demand:
    """一个市场需求"""
    demand_id: str
    requester_id: str     # 谁发出的需求
    capability_needed: str
    description: str
    max_budget: float
    deadline_hours: float = 24.0
    status: str = "open"  # open / bidding / filled / cancelled
    created_at: float = field(default_factory=time.time)


@dataclass
class Bid:
    """一个竞标"""
    bid_id: str
    demand_id: str
    bidder_id: str        # 竞标 Agent
    price: float
    estimated_quality: float
    estimated_hours: float
    rationale: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class Deal:
    """成交记录"""
    deal_id: str
    demand_id: str
    winner_id: str
    requester_id: str
    price: float
    escrow_id: str = ""
    status: str = "active"  # active / completed / disputed
    created_at: float = field(default_factory=time.time)


@dataclass
class BiddingEngine:
    """竞标引擎——供需匹配"""

    demands: dict[str, Demand] = field(default_factory=dict)
    bids: dict[str, list[Bid]] = field(default_factory=dict)  # demand_id → bids
    deals: list[Deal] = field(default_factory=list)
    directory: ServiceDirectory = field(default_factory=ServiceDirectory)
    _path: Path = config.data_dir / "bidding.json"

    def __post_init__(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self.demands = {d["demand_id"]: Demand(**d) for d in data.get("demands", [])}
                self.deals = [Deal(**d) for d in data.get("deals", [])]
            except (json.JSONDecodeError, OSError):
                pass

    def post_demand(
        self,
        requester_id: str,
        capability: str,
        description: str,
        max_budget: float,
        deadline_hours: float = 24.0,
    ) -> Demand:
        """广播一个需求到市场"""
        import hashlib
        raw = f"{requester_id}{capability}{time.time()}"
        demand_id = hashlib.sha256(raw.encode()).hexdigest()[:12]

        demand = Demand(
            demand_id=demand_id,
            requester_id=requester_id,
            capability_needed=capability,
            description=description,
            max_budget=max_budget,
            deadline_hours=deadline_hours,
            status="bidding",
        )
        self.demands[demand_id] = demand

        # 自动匹配并通知潜在供应商
        self._match_and_notify(demand)

        self._save()
        return demand

    def _match_and_notify(self, demand: Demand):
        """匹配能处理此需求的 Agent"""
        candidates = self.directory.find_by_capability(demand.capability_needed)
        if not candidates:
            demand.status = "open"
            return

        demand.status = "bidding"

    def place_bid(
        self,
        demand_id: str,
        bidder_id: str,
        price: float,
        estimated_quality: float = 0.7,
        estimated_hours: float = 4.0,
    ) -> Bid | None:
        """Agent 对一个需求出价"""
        if demand_id not in self.demands:
            return None

        demand = self.demands[demand_id]
        if price > demand.max_budget:
            return None

        import hashlib
        raw = f"{demand_id}{bidder_id}{time.time()}"
        bid_id = hashlib.sha256(raw.encode()).hexdigest()[:12]

        bid = Bid(
            bid_id=bid_id,
            demand_id=demand_id,
            bidder_id=bidder_id,
            price=price,
            estimated_quality=estimated_quality,
            estimated_hours=estimated_hours,
        )

        if demand_id not in self.bids:
            self.bids[demand_id] = []
        self.bids[demand_id].append(bid)
        self._save()
        return bid

    def select_winner(self, demand_id: str) -> Bid | None:
        """选出最优竞标（性价比最高）"""
        demand_bids = self.bids.get(demand_id, [])
        if not demand_bids:
            return None

        demand = self.demands.get(demand_id)
        if not demand:
            return None

        # 评分 = quality / (price * hours)——单位时间/成本的回报
        def score(b: Bid) -> float:
            return b.estimated_quality / max(b.price * b.estimated_hours, 0.01)

        winner = max(demand_bids, key=score)
        demand.status = "filled"

        import hashlib
        raw = f"{demand_id}{winner.bidder_id}{time.time()}"
        deal_id = hashlib.sha256(raw.encode()).hexdigest()[:12]

        deal = Deal(
            deal_id=deal_id,
            demand_id=demand_id,
            winner_id=winner.bidder_id,
            requester_id=demand.requester_id,
            price=winner.price,
        )
        self.deals.append(deal)
        self._save()
        return winner

    def active_demands(self) -> list[Demand]:
        return [d for d in self.demands.values() if d.status in ("open", "bidding")]

    def stats(self) -> dict:
        won = sum(1 for d in self.demands.values() if d.status == "filled")
        total_bids = sum(len(b) for b in self.bids.values())
        avg_bids = total_bids / max(len(self.demands), 1)
        return {
            "total_demands": len(self.demands),
            "filled": won,
            "fill_rate": won / max(len(self.demands), 1),
            "total_bids": total_bids,
            "avg_bids_per_demand": round(avg_bids, 1),
            "total_deals": len(self.deals),
            "total_volume": sum(d.price for d in self.deals),
        }

    def _save(self):
        self._path.write_text(json.dumps({
            "demands": [{k: v for k, v in d.__dict__.items()} for d in self.demands.values()],
            "deals": [{k: v for k, v in d.__dict__.items()} for d in self.deals],
        }, indent=2))
