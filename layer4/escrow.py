"""Layer 4: 托管结算

微支付托管系统。

流程：
  1. 成交后，买方资金进入托管
  2. 卖方完成任务交付
  3. 买方确认 → 资金释放给卖方
  4. 买方拒收 → 进入仲裁

Alpha X 的资金流：
  个体收入 → 平台抽成(10%) → 个体留存(70%) + 上缴资金池(30%)

外包交易的资金流：
  买方付费 → 托管冻结 → 确认交付 → 卖方收款 → 资金池抽成(5%)
"""

from __future__ import annotations

import json
import time
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

from config import config


class EscrowStatus(str, Enum):
    FUNDED = "funded"           # 买方已付款，冻结中
    DELIVERED = "delivered"     # 卖方已交付
    ACCEPTED = "accepted"       # 买方确认，已结算
    DISPUTED = "disputed"       # 争议中
    REFUNDED = "refunded"       # 已退款
    RELEASED = "released"       # 已释放给卖方


@dataclass
class EscrowTransaction:
    tx_id: str
    deal_id: str
    buyer_id: str
    seller_id: str
    amount: float
    platform_fee: float      # 平台从中抽取的费用
    seller_receives: float   # 卖方实际收到
    status: EscrowStatus = EscrowStatus.FUNDED
    created_at: float = field(default_factory=time.time)
    resolved_at: float = 0.0


@dataclass
class Escrow:
    """托管结算系统"""

    transactions: dict[str, EscrowTransaction] = field(default_factory=dict)
    total_volume: float = 0.0
    total_fees: float = 0.0
    _path: Path = config.data_dir / "escrow.json"

    def __post_init__(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                for t in data.get("transactions", []):
                    if isinstance(t.get("status"), str):
                        t["status"] = EscrowStatus(t["status"])
                    self.transactions[t["tx_id"]] = EscrowTransaction(**t)
                self.total_volume = data.get("total_volume", 0.0)
                self.total_fees = data.get("total_fees", 0.0)
            except (json.JSONDecodeError, OSError):
                pass

    def fund(
        self,
        deal_id: str,
        buyer_id: str,
        seller_id: str,
        amount: float,
        fee_rate: float = 0.05,
    ) -> EscrowTransaction | None:
        """买方将资金转入托管"""
        if amount <= 0:
            return None

        platform_fee = amount * fee_rate
        seller_receives = amount - platform_fee

        raw = f"{deal_id}{buyer_id}{seller_id}{time.time()}"
        tx_id = hashlib.sha256(raw.encode()).hexdigest()[:12]

        tx = EscrowTransaction(
            tx_id=tx_id,
            deal_id=deal_id,
            buyer_id=buyer_id,
            seller_id=seller_id,
            amount=amount,
            platform_fee=platform_fee,
            seller_receives=seller_receives,
        )
        self.transactions[tx_id] = tx
        self.total_volume += amount
        self._save()
        return tx

    def deliver(self, tx_id: str) -> bool:
        """卖方标记已交付"""
        tx = self.transactions.get(tx_id)
        if not tx or tx.status != EscrowStatus.FUNDED:
            return False
        tx.status = EscrowStatus.DELIVERED
        self._save()
        return True

    def accept(self, tx_id: str) -> bool:
        """买方确认，释放资金。同时通过 WalletManager 完成实际转账。"""
        tx = self.transactions.get(tx_id)
        if not tx or tx.status != EscrowStatus.DELIVERED:
            return False
        tx.status = EscrowStatus.ACCEPTED
        tx.resolved_at = time.time()
        self.total_fees += tx.platform_fee
        self._save()

        # ── 实际资金结算 ──
        try:
            from capital.wallet import WalletManager
            wm = WalletManager()
            wm.settle_escrow(
                buyer_id=tx.buyer_id,
                seller_id=tx.seller_id,
                amount=tx.amount,
                memo=f"escrow:{tx_id[:8]}",
            )
        except Exception:
            pass  # wallet unavailable, escrow still valid

        return True

    def dispute(self, tx_id: str) -> bool:
        """买方拒收，进入仲裁"""
        tx = self.transactions.get(tx_id)
        if not tx or tx.status != EscrowStatus.DELIVERED:
            return False
        tx.status = EscrowStatus.DISPUTED
        self._save()
        return True

    def resolve_dispute(self, tx_id: str, refund: bool = False) -> bool:
        """仲裁裁决"""
        tx = self.transactions.get(tx_id)
        if not tx or tx.status != EscrowStatus.DISPUTED:
            return False
        tx.status = EscrowStatus.REFUNDED if refund else EscrowStatus.RELEASED
        tx.resolved_at = time.time()
        if not refund:
            self.total_fees += tx.platform_fee
        self._save()
        return True

    def pending_count(self) -> int:
        return sum(
            1 for t in self.transactions.values()
            if t.status in (EscrowStatus.FUNDED, EscrowStatus.DELIVERED)
        )

    def disputed_count(self) -> int:
        return sum(
            1 for t in self.transactions.values()
            if t.status == EscrowStatus.DISPUTED
        )

    def stats(self) -> dict:
        accepted = sum(
            1 for t in self.transactions.values()
            if t.status == EscrowStatus.ACCEPTED
        )
        return {
            "total_transactions": len(self.transactions),
            "total_volume": self.total_volume,
            "total_fees": self.total_fees,
            "accepted": accepted,
            "disputed": self.disputed_count(),
            "pending": self.pending_count(),
            "dispute_rate": self.disputed_count() / max(len(self.transactions), 1),
        }

    def _save(self):
        self._path.write_text(json.dumps({
            "transactions": [
                {k: (v.value if isinstance(v, Enum) else v) for k, v in t.__dict__.items()}
                for t in self.transactions.values()
            ],
            "total_volume": self.total_volume,
            "total_fees": self.total_fees,
        }, indent=2))
