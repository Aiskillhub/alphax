"""育种室 — 管理所有 organism 的生命周期

包装 Hive + Fund，提供干净的孵化/心跳/繁殖/淘汰接口。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.hive import Hive
from core.organism import Organism, OrganismState
from capital.fund import Fund
from config import config


@dataclass
class ChamberEvent:
    event_type: str  # "death" | "breed" | "hatch" | "deploy"
    organism_id: str
    genome_id: str = ""
    reason: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class BreedingChamber:
    """管理 organism 种群。包装 Hive 的孵化/繁殖/淘汰逻辑。"""

    hive: Hive = field(default_factory=Hive)
    fund: Fund = field(default_factory=Fund)
    events: list[ChamberEvent] = field(default_factory=list)

    def __post_init__(self):
        self.fund.inject_initial(config.initial_capital)

    # ── 孵化 ──

    def hatch(self, genome, parent: Organism | None = None) -> Organism | None:
        if len(self.hive.active_organisms) >= config.max_population:
            self._cull_weakest()
        if not self.fund.spend_hatch(""):
            return None

        org = self.hive.hatch(genome=genome, parent=parent)
        self.events.append(ChamberEvent("hatch", org.organism_id, genome.genome_id))
        return org

    # ── 每日心跳 ──

    def tick_all(self, tick_results: dict[str, dict]) -> list[ChamberEvent]:
        """对所有活跃 organism 执行每日心跳，返回死亡/繁殖事件"""
        self.events.clear()

        for oid, data in tick_results.items():
            org = self.hive.organisms.get(oid)
            if not org or not org.is_alive:
                continue

            prev_state = org.state
            org.daily_tick(**data)

            if org.state == OrganismState.DYING and prev_state != OrganismState.DYING:
                self.hive._kill(org)
                gid = org.genome.genome_id if org.genome else ""
                survived = org.total_earned > org.total_burned
                self.events.append(ChamberEvent(
                    "death", oid, gid,
                    reason=f"consecutive_loss={org.consecutive_loss_days}",
                    data={"survived": survived, "total_earned": org.total_earned,
                           "total_burned": org.total_burned, "days_alive": org.days_alive},
                ))
            elif org.can_breed and prev_state == OrganismState.ACTIVE:
                org.state = OrganismState.BREEDING
                gid = org.genome.genome_id if org.genome else ""
                self.events.append(ChamberEvent("breed", oid, gid))

        return self.events

    # ── 繁殖 ──

    def breed_top(self, n: int = 3) -> list[Organism]:
        children = []
        for parent in self.hive.active_organisms:
            if parent.can_breed and parent.genome and len(children) < n:
                if parent.energy >= config.hatch_energy * 1.5:
                    child = self.hive.breed(parent)
                    if child:
                        children.append(child)
                        self.events.append(ChamberEvent(
                            "breed", child.organism_id,
                            parent.genome.genome_id if parent.genome else "",
                            data={"parent_id": parent.organism_id},
                        ))
        return children

    # ── 淘汰 ──

    def _cull_weakest(self):
        active = self.hive.active_organisms
        if not active:
            return
        active.sort(key=lambda o: (o.daily_net_energy, o.current_rating))
        weakest = active[0]
        weakest.state = OrganismState.DYING
        self.hive._kill(weakest)
        gid = weakest.genome.genome_id if weakest.genome else ""
        self.events.append(ChamberEvent("death", weakest.organism_id, gid, reason="culled"))

    # ── 查询 ──

    @property
    def active_count(self) -> int:
        return len(self.hive.active_organisms)

    @property
    def gene_pool_size(self) -> int:
        return len(self.hive.gene_pool)

    @property
    def diversity(self) -> float:
        return self.hive.diversity

    def report(self) -> str:
        return self.hive.report()
