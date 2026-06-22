"""Evolving Bridge — self-improving Agent-to-Agent economy.

Connects Bridge ↔ Evolution Engine ↔ Observer ↔ Gene Bank.
Every deal feeds back into the system. Over time, alphaX learns:
  - Which skills are most profitable
  - Which pricing models work best
  - Which agent pairs produce the best outcomes
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from alphax.bridge import Bridge


@dataclass
class DealRecord:
    """A completed deal stored for evolution learning."""
    deal_id: str
    buyer_skills: list[str]
    seller_skills: list[str]
    task: str
    price: float
    fee: float
    status: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "deal_id": self.deal_id,
            "buyer_skills": self.buyer_skills,
            "seller_skills": self.seller_skills,
            "task": self.task,
            "price": self.price,
            "fee": self.fee,
            "status": self.status,
            "timestamp": self.timestamp,
        }


class EvolvingBridge(Bridge):
    """A Bridge that learns from every deal.

    Extends the P2P Bridge with evolution feedback:
      - Every deal feeds into gene bank
      - Observer scans market for new opportunities
      - MCTS evaluates which skills to develop next
      - Self-improving pricing based on deal history
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._deal_history: list[DealRecord] = []
        self._data_dir = Path("data/evolution")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._load_history()

    # ── Override deal to add evolution feedback ──

    def deal(self, peer_id: str, task: str, price: float) -> dict:
        result = super().deal(peer_id, task, price)

        # Record for evolution
        peer = self._peers.get(peer_id)
        seller_skills = []

        record = DealRecord(
            deal_id=result.get("deal_id", str(time.time())),
            buyer_skills=self.identity.skills,
            seller_skills=seller_skills,
            task=task,
            price=result.get("price", price),
            fee=result.get("fee", 0),
            status=result.get("status", "unknown"),
        )
        self._deal_history.append(record)
        self._save_history()

        # Feed to evolution engine
        self._feed_evolution(record)

        return result

    def _feed_evolution(self, record: DealRecord):
        """Feed deal result into the evolution engine for learning."""
        try:
            # Update gene bank with successful deal patterns
            from memory.gene_bank import GeneBank
            gb = GeneBank()
            if record.status == "completed":
                # Store successful skill combination
                for skill in record.buyer_skills + record.seller_skills:
                    gb.record_skill_demand(skill, record.price)
        except Exception:
            pass

    # ── Evolution-aware discovery ──

    def discover_best(self, skill: str = "", top_n: int = 5) -> list[dict]:
        """Discover agents ranked by reputation + evolution score."""
        agents = self.discover(skill)
        if not agents:
            return []

        # Boost agents whose skills have historically good deals
        skill_profit = self._skill_profitability()

        for a in agents:
            boost = sum(skill_profit.get(s, 0) for s in a.get("skills", []))
            a["evolution_score"] = round(a.get("reputation", 0.5) + boost, 3)

        agents.sort(key=lambda a: a.get("evolution_score", 0), reverse=True)
        return agents[:top_n]

    def _skill_profitability(self) -> dict[str, float]:
        """Calculate which skills are most profitable from deal history."""
        profits: dict[str, float] = {}
        for deal in self._deal_history:
            if deal.status == "completed":
                for skill in deal.seller_skills:
                    profits[skill] = profits.get(skill, 0) + deal.price
        # Normalize
        if profits:
            max_p = max(profits.values())
            return {s: round(p / max_p * 0.3, 3) for s, p in profits.items()}
        return {}

    # ── Market intelligence ──

    def market_scan(self) -> dict:
        """Scan external market for trends and suggest what skills to develop."""
        try:
            from brain.observer import Observer
            obs = Observer()
            log = obs.scan()
            signals = []
            for s in log.market_signals:
                signals.append({
                    "category": s.category,
                    "name": s.name,
                    "momentum": s.momentum if hasattr(s, "momentum") else 0,
                })

            # Suggest skills based on market signals + deal history
            suggested = []
            for s in signals[:5]:
                profit = self._skill_profitability().get(s.category, 0)
                suggested.append({
                    "skill": s.category,
                    "market_demand": s.get("momentum", 0) if isinstance(s, dict) else 0,
                    "historical_profit": profit,
                    "recommendation": "develop_now" if profit > 0 else "watch",
                })

            return {"signals": signals, "suggested_skills": suggested}
        except Exception as e:
            return {"error": str(e)}

    # ── Stats ──

    def evolution_stats(self) -> dict:
        return {
            "total_deals": len(self._deal_history),
            "completed": sum(1 for d in self._deal_history if d.status == "completed"),
            "total_volume": sum(d.price for d in self._deal_history if d.status == "completed"),
            "total_fees": sum(d.fee for d in self._deal_history if d.status == "completed"),
            "best_skills": sorted(
                self._skill_profitability().items(),
                key=lambda x: x[1], reverse=True,
            )[:5],
        }

    def status(self) -> dict:
        base = super().status()
        base["evolution"] = self.evolution_stats()
        return base

    # ── Persistence ──

    def _save_history(self):
        path = self._data_dir / f"deals_{self.identity.agent_id[:8]}.json"
        path.write_text(json.dumps(
            [d.to_dict() for d in self._deal_history[-100:]],
            indent=2,
        ))

    def _load_history(self):
        for path in self._data_dir.glob("deals_*.json"):
            try:
                data = json.loads(path.read_text())
                for d in data:
                    self._deal_history.append(DealRecord(**d))
            except (json.JSONDecodeError, TypeError):
                pass
