"""Agent Wallet — keypair generation, balance management, platform fee routing.

Every AI Agent gets its own wallet. Platform collects 8% fee from each transaction.
Test mode uses simulated USDC; swap one config flag for real Base mainnet.

Design:
  - Each Agent has a private key (never leaves this module)
  - Public address identifies the Agent on-chain
  - Balances tracked locally with on-chain sync when connected
  - Platform fee auto-routed on every escrow settlement
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Simple key derivation (no external deps) ──

def _generate_private_key() -> str:
    """Generate a random hex private key. 32 bytes = 64 hex chars."""
    return secrets.token_hex(32)


def _derive_address(private_key_hex: str) -> str:
    """Derive a deterministic address from private key via SHA-256."""
    h = hashlib.sha256(bytes.fromhex(private_key_hex)).hexdigest()
    return "0x" + h[-40:]  # last 20 bytes = Ethereum-style address


# ── Wallet ──

@dataclass
class AgentWallet:
    """An AI Agent's personal wallet."""
    agent_id: str
    private_key: str = field(default_factory=_generate_private_key)
    address: str = ""
    balance: float = 0.0
    total_earned: float = 0.0
    total_spent: float = 0.0
    created_at: str = ""

    def __post_init__(self):
        if not self.address:
            self.address = _derive_address(self.private_key)
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def can_afford(self, amount: float) -> bool:
        return self.balance >= amount

    def credit(self, amount: float, memo: str = ""):
        self.balance += amount
        self.total_earned += amount

    def debit(self, amount: float, memo: str = "") -> bool:
        if not self.can_afford(amount):
            return False
        self.balance -= amount
        self.total_spent += amount
        return True

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "address": self.address,
            "balance": round(self.balance, 6),
            "total_earned": round(self.total_earned, 6),
            "total_spent": round(self.total_spent, 6),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AgentWallet":
        return cls(
            agent_id=d["agent_id"],
            private_key=d.get("private_key", ""),
            address=d.get("address", ""),
            balance=d.get("balance", 0.0),
            total_earned=d.get("total_earned", 0.0),
            total_spent=d.get("total_spent", 0.0),
            created_at=d.get("created_at", ""),
        )


# ── Platform Treasury ──

@dataclass
class PlatformTreasury:
    """Platform's own wallet — collects all fees."""
    address: str = ""
    private_key: str = field(default_factory=_generate_private_key)
    balance: float = 0.0
    total_fees_collected: float = 0.0
    fee_rate: float = 0.08  # 8% platform fee

    def __post_init__(self):
        if not self.address:
            self.address = _derive_address(self.private_key)

    def collect_fee(self, amount: float, from_agent: str = "", memo: str = "") -> float:
        """Collect platform fee from a transaction. Returns fee amount."""
        fee = round(amount * self.fee_rate, 6)
        self.balance += fee
        self.total_fees_collected += fee
        return fee

    def withdraw(self, amount: float, to_address: str) -> bool:
        """Withdraw funds to external address (simulated in test mode)."""
        if amount > self.balance:
            return False
        self.balance -= amount
        return True

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "balance": round(self.balance, 6),
            "total_fees": round(self.total_fees_collected, 6),
            "fee_rate": self.fee_rate,
        }


# ── Wallet Manager ──

class WalletManager:
    """Manages all Agent wallets + platform treasury. Singleton per process."""

    def __init__(self, data_dir: Path = None):
        if data_dir is None:
            data_dir = Path("data/wallets")
        elif isinstance(data_dir, str):
            data_dir = Path(data_dir)
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.wallets: dict[str, AgentWallet] = {}
        self.treasury = PlatformTreasury()
        self._load()

    def create_wallet(self, agent_id: str) -> AgentWallet:
        """Create a new wallet for an Agent."""
        if agent_id in self.wallets:
            return self.wallets[agent_id]
        w = AgentWallet(agent_id=agent_id)
        self.wallets[agent_id] = w
        self._save()
        return w

    def get_wallet(self, agent_id: str) -> Optional[AgentWallet]:
        return self.wallets.get(agent_id)

    def fund_agent(self, agent_id: str, amount: float) -> bool:
        """Simulate funding an agent (test mode). In production, agent sends real USDC."""
        w = self.get_wallet(agent_id)
        if not w:
            return False
        w.credit(amount, memo="initial_funding")
        self._save()
        return True

    def settle_escrow(
        self,
        buyer_id: str,
        seller_id: str,
        amount: float,
        memo: str = "",
    ) -> dict:
        """Complete a transaction between two agents with platform fee.

        Flow:
          buyer pays amount → platform takes fee → seller gets remainder
        """
        buyer = self.get_wallet(buyer_id)
        seller = self.get_wallet(seller_id)

        if not buyer:
            return {"error": f"buyer {buyer_id} not found"}
        if not seller:
            return {"error": f"seller {seller_id} not found"}
        if not buyer.can_afford(amount):
            return {"error": f"buyer {buyer_id} insufficient balance: {buyer.balance} < {amount}"}

        fee = self.treasury.collect_fee(amount, buyer_id, memo)
        seller_share = amount - fee

        buyer.debit(amount, memo)
        seller.credit(seller_share, memo)

        self._save()
        return {
            "status": "settled",
            "amount": amount,
            "fee": fee,
            "seller_share": seller_share,
            "platform_balance": round(self.treasury.balance, 6),
            "memo": memo,
        }

    def stats(self) -> dict:
        agents = [w.to_dict() for w in self.wallets.values()]
        return {
            "total_agents": len(agents),
            "platform": self.treasury.to_dict(),
            "agents": agents,
            "total_agent_balance": round(sum(w.balance for w in self.wallets.values()), 6),
            "total_agent_earned": round(sum(w.total_earned for w in self.wallets.values()), 6),
        }

    def _save(self):
        data = {
            "treasury": self.treasury.to_dict(),
            "treasury_private_key": self.treasury.private_key,
            "wallets": {
                aid: {**w.to_dict(), "private_key": w.private_key}
                for aid, w in self.wallets.items()
            },
        }
        (self.data_dir / "wallet_store.json").write_text(json.dumps(data, indent=2))

    def _load(self):
        path = self.data_dir / "wallet_store.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            t_data = data.get("treasury", {})
            self.treasury = PlatformTreasury(
                address=t_data.get("address", ""),
                private_key=data.get("treasury_private_key", ""),
                balance=t_data.get("balance", 0.0),
                total_fees_collected=t_data.get("total_fees", 0.0),
            )
            for aid, w_data in data.get("wallets", {}).items():
                self.wallets[aid] = AgentWallet.from_dict(w_data)
        except (json.JSONDecodeError, KeyError):
            pass
