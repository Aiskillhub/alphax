"""个体生命周期管理

每个 Organism 是一个活的数字实体：
  Hatch → Grow → Earn → Breed or Die → Legacy

状态机：
  HATCHING → ACTIVE → BREEDING / DYING → DEAD
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from core.genome import Genome

from config import config


class OrganismState(str, Enum):
    HATCHING = "hatching"     # 孵化中：基因 → 产品代码
    DEPLOYING = "deploying"   # 部署中：上架
    ACTIVE = "active"         # 活跃：在市场中赚钱
    REPAIRING = "repairing"   # 修复中：自动修 bug
    BREEDING = "breeding"     # 繁殖：产生后代
    DYING = "dying"           # 死亡中：下架、清算
    DEAD = "dead"             # 已死亡


@dataclass
class DailyRecord:
    date: str
    energy_delta: float      # 当日能量变化
    income: float            # 当日收入
    cost: float              # 当日消耗
    downloads: int           # 当日下载量
    rating: float | None     # 当日评分


@dataclass
class Organism:
    organism_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    genome: Genome | None = None
    state: OrganismState = OrganismState.HATCHING

    # 能量系统
    energy: float = 0.0             # 当前能量余额
    total_earned: float = 0.0       # 累计收入
    total_burned: float = 0.0       # 累计消耗
    daily_history: list[DailyRecord] = field(default_factory=list)

    # 存活指标
    days_alive: int = 0
    days_energy_positive: int = 0
    consecutive_loss_days: int = 0

    # 市场表现
    gumroad_product_id: str = ""
    agistore_skill_id: str = ""
    chrome_store_id: str = ""
    current_rating: float = 0.0
    total_reviews: int = 0
    total_downloads: int = 0

    # 时间
    hatched_at: str = ""
    deployed_at: str = ""
    died_at: str = ""

    # 谱系
    parent_organism_id: str = ""

    @property
    def is_alive(self) -> bool:
        return self.state in {
            OrganismState.ACTIVE,
            OrganismState.REPAIRING,
            OrganismState.BREEDING,
        }

    @property
    def daily_net_energy(self) -> float:
        """最近 7 天日均净能量"""
        if not self.daily_history:
            return 0.0
        recent = self.daily_history[-7:]
        return sum(r.energy_delta for r in recent) / len(recent)

    @property
    def can_breed(self) -> bool:
        return (
            self.days_alive >= config.breed_min_days
            and self.days_energy_positive >= config.breed_min_energy_positive_days
            and self.is_alive
        )

    @property
    def should_die(self) -> bool:
        return (
            self.consecutive_loss_days >= config.survival_threshold_days
            or self.energy <= 0
        )

    def hatch(self, genome: Genome, initial_energy: float = None) -> None:
        """孵化：注入基因，初始化能量"""
        self.genome = genome
        self.energy = initial_energy or config.hatch_energy
        self.state = OrganismState.HATCHING
        self.hatched_at = datetime.now(timezone.utc).isoformat()

    def deploy(self) -> None:
        """部署完成，进入市场"""
        self.state = OrganismState.ACTIVE
        self.deployed_at = datetime.now(timezone.utc).isoformat()

    def daily_tick(self, income: float = 0.0, downloads: int = 0,
                   rating: float | None = None, api_cost: float = 0.0) -> DailyRecord:
        """每日心跳：更新能量、检查生死"""
        burn = config.daily_burn_rate + api_cost
        net = income - burn

        self.energy += net
        self.total_earned += income
        self.total_burned += burn
        self.days_alive += 1

        if net > 0:
            self.days_energy_positive += 1
            self.consecutive_loss_days = 0
        else:
            self.consecutive_loss_days += 1

        if downloads > 0:
            self.total_downloads += downloads
        if rating is not None:
            self.current_rating = rating

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        record = DailyRecord(
            date=today,
            energy_delta=net,
            income=income,
            cost=burn,
            downloads=downloads,
            rating=rating,
        )
        self.daily_history.append(record)

        if self.should_die:
            self.state = OrganismState.DYING

        return record

    def die(self) -> None:
        """死亡：记录终止状态"""
        self.state = OrganismState.DEAD
        self.died_at = datetime.now(timezone.utc).isoformat()

        if self.genome:
            self.genome.times_used += 1
            if self.total_earned > self.total_burned:
                self.genome.times_succeeded += 1

    def to_dict(self) -> dict:
        return {
            "organism_id": self.organism_id,
            "genome": self.genome.to_dict() if self.genome else None,
            "state": self.state.value,
            "energy": self.energy,
            "total_earned": self.total_earned,
            "total_burned": self.total_burned,
            "days_alive": self.days_alive,
            "days_energy_positive": self.days_energy_positive,
            "consecutive_loss_days": self.consecutive_loss_days,
            "gumroad_product_id": self.gumroad_product_id,
            "agistore_skill_id": self.agistore_skill_id,
            "current_rating": self.current_rating,
            "total_reviews": self.total_reviews,
            "total_downloads": self.total_downloads,
            "hatched_at": self.hatched_at,
            "deployed_at": self.deployed_at,
            "died_at": self.died_at,
            "parent_organism_id": self.parent_organism_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Organism:
        o = cls(
            organism_id=d["organism_id"],
            state=OrganismState(d["state"]),
            energy=d["energy"],
            total_earned=d["total_earned"],
            total_burned=d["total_burned"],
        )
        if d.get("genome"):
            o.genome = Genome.from_dict(d["genome"])
        o.days_alive = d.get("days_alive", 0)
        o.days_energy_positive = d.get("days_energy_positive", 0)
        o.consecutive_loss_days = d.get("consecutive_loss_days", 0)
        o.gumroad_product_id = d.get("gumroad_product_id", "")
        o.agistore_skill_id = d.get("agistore_skill_id", "")
        o.current_rating = d.get("current_rating", 0.0)
        o.total_downloads = d.get("total_downloads", 0)
        o.hatched_at = d.get("hatched_at", "")
        o.deployed_at = d.get("deployed_at", "")
        o.died_at = d.get("died_at", "")
        o.parent_organism_id = d.get("parent_organism_id", "")
        return o
