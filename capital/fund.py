"""AlphaX 资金管理

资金流：
  收入 → 平台抽成(10%) → 个体留存(70%) + 上缴资金池(30%)
  资金池用于孵化新个体和日常运维
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class Transaction:
    tx_id: str
    tx_type: str  # "income" | "hatch_cost" | "platform_fee" | "pool_contribution" | "burn"
    amount: float
    organism_id: str = ""
    description: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Fund:
    """资金池——管理 AlphaX 的所有资金流动"""

    pool_balance: float = 0.0
    total_platform_fees: float = 0.0
    total_hatch_costs: float = 0.0
    transactions: list[Transaction] = field(default_factory=list)
    _path: Path | None = None

    def __post_init__(self):
        if self._path is None:
            self._path = config.data_dir / "fund.json"
        config.data_dir.mkdir(exist_ok=True)
        if self._path.exists():
            try:
                self.load()
            except (json.JSONDecodeError, OSError):
                pass

    # ── 资金流 ──

    def distribute_income(self, income: float, organism_id: str = "") -> dict:
        """收入分配：平台抽成 → 资金池 → 个体留存"""
        platform_fee = income * config.platform_fee_rate
        remaining = income - platform_fee
        pool_contribution = remaining * config.pool_share
        organism_share = remaining * config.organism_energy_share

        self.pool_balance += pool_contribution
        self.total_platform_fees += platform_fee

        self._record(Transaction(
            tx_id=f"tx_{len(self.transactions):06d}",
            tx_type="income",
            amount=income,
            organism_id=organism_id,
            description=f"收入 ${income:.2f} → 平台费 ${platform_fee:.2f} + 池 ${pool_contribution:.2f} + 个体 ${organism_share:.2f}",
        ))

        return {
            "income": income,
            "platform_fee": platform_fee,
            "pool_contribution": pool_contribution,
            "organism_share": organism_share,
        }

    def spend_hatch(self, organism_id: str) -> bool:
        """孵化支出"""
        cost = config.hatch_energy
        if self.pool_balance >= cost:
            self.pool_balance -= cost
            self.total_hatch_costs += cost
            self._record(Transaction(
                tx_id=f"tx_{len(self.transactions):06d}",
                tx_type="hatch_cost",
                amount=-cost,
                organism_id=organism_id,
                description=f"孵化成本 ${cost:.2f}",
            ))
            return True
        return False

    def inject_initial(self, amount: float = None) -> float:
        """注入初始资金"""
        amt = amount or config.initial_capital
        self.pool_balance += amt
        self._record(Transaction(
            tx_id=f"tx_{len(self.transactions):06d}",
            tx_type="income",
            amount=amt,
            description=f"初始资金注入 ${amt:.2f}",
        ))
        return self.pool_balance

    # ── 查询 ──

    @property
    def can_hatch(self) -> bool:
        return self.pool_balance >= config.hatch_energy

    @property
    def summary(self) -> dict:
        return {
            "pool_balance": self.pool_balance,
            "total_platform_fees": self.total_platform_fees,
            "total_hatch_costs": self.total_hatch_costs,
            "transaction_count": len(self.transactions),
        }

    # ── 持久化 ──

    def save(self):
        self._path.write_text(json.dumps({
            "pool_balance": self.pool_balance,
            "total_platform_fees": self.total_platform_fees,
            "total_hatch_costs": self.total_hatch_costs,
            "transactions": [
                {k: v for k, v in t.__dict__.items()} for t in self.transactions
            ],
        }, indent=2))

    def load(self):
        data = json.loads(self._path.read_text())
        self.pool_balance = data.get("pool_balance", 0)
        self.total_platform_fees = data.get("total_platform_fees", 0)
        self.total_hatch_costs = data.get("total_hatch_costs", 0)
        self.transactions = [Transaction(**t) for t in data.get("transactions", [])]

    def _record(self, tx: Transaction):
        self.transactions.append(tx)
        self.save()
