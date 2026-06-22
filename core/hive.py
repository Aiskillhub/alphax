"""AlphaX 蜂巢 — 种群管理器

职责：
  1. 维护活跃个体列表
  2. 裁决繁殖请求（适应度 > 阈值才能繁殖）
  3. 裁决死亡（连续亏损 → 终止）
  4. 维护种群多样性
  5. 执行每日心跳
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field

from core.genome import Genome, SEED_GENOMES
from core.organism import Organism, OrganismState
from config import config


@dataclass
class Hive:
    organisms: dict[str, Organism] = field(default_factory=dict)
    gene_pool: dict[str, Genome] = field(default_factory=dict)
    dead_organisms: list[Organism] = field(default_factory=list)

    # ── 孵化 ──

    def hatch(
        self,
        genome: Genome | None = None,
        parent: Organism | None = None,
        strategy: str = "inherit",
    ) -> Organism:
        if len(self.active_organisms) >= config.max_population:
            self._cull_weakest()

        if strategy == "explore":
            genome = self._random_genome()
        elif strategy == "seed":
            genome = random.choice(SEED_GENOMES).mutate()
        elif genome is None:
            genome = self._select_genome()

        org = Organism()
        org.hatch(genome, config.hatch_energy)
        if parent:
            org.parent_organism_id = parent.organism_id

        self.organisms[org.organism_id] = org
        return org

    def hatch_batch(self, count: int, strategy: str = "inherit") -> list[Organism]:
        return [self.hatch(strategy=strategy) for _ in range(count)]

    # ── 每日心跳 ──

    def tick_all(self, monitor_results: dict[str, dict]) -> list[str]:
        events = []
        for oid, data in monitor_results.items():
            org = self.organisms.get(oid)
            if not org or not org.is_alive:
                continue
            prev = org.state
            org.daily_tick(**data)
            if org.state == OrganismState.DYING and prev != OrganismState.DYING:
                self._kill(org)
                name = org.genome.express() if org.genome else "unknown"
                events.append(f"DEATH:{oid}:{name}")
            elif org.can_breed and prev == OrganismState.ACTIVE:
                org.state = OrganismState.BREEDING
                events.append(f"BREED_READY:{oid}:fitness={org.genome.fitness_score:.2f}")
        return events

    # ── 繁殖 ──

    def breed(self, parent: Organism) -> Organism | None:
        if not parent.can_breed or not parent.genome:
            return None
        if parent.energy < config.hatch_energy * 1.5:
            return None
        child = self.hatch(genome=parent.genome.mutate(), parent=parent)
        parent.state = OrganismState.ACTIVE
        return child

    def breed_top(self, n: int = 3) -> list[Organism]:
        eligible = [o for o in self.active_organisms if o.can_breed and o.genome]
        eligible.sort(key=lambda o: o.genome.fitness_score, reverse=True)
        children = []
        for parent in eligible[:n]:
            child = self.breed(parent)
            if child:
                children.append(child)
        return children

    # ── 死亡 ──

    def _kill(self, org: Organism) -> None:
        org.die()
        self.dead_organisms.append(org)
        if org.genome:
            self._update_gene_pool(org.genome)

    def _cull_weakest(self) -> None:
        active = self.active_organisms
        if not active:
            return
        active.sort(key=lambda o: (o.daily_net_energy, o.current_rating))
        active[0].state = OrganismState.DYING
        self._kill(active[0])

    # ── 基因库 ──

    def _select_genome(self) -> Genome:
        if not self.gene_pool:
            return random.choice(SEED_GENOMES).mutate()
        genomes = list(self.gene_pool.values())
        if random.random() < config.exploration_budget:
            return random.choice(genomes).mutate()
        weights = [max(g.fitness_score, 0.01) for g in genomes]
        probs = [w / sum(weights) for w in weights]
        return random.choices(genomes, weights=probs, k=1)[0]

    def _random_genome(self) -> Genome:
        return random.choice(SEED_GENOMES).mutate()

    def _update_gene_pool(self, genome: Genome) -> None:
        gid = genome.genome_id
        if gid in self.gene_pool:
            old = self.gene_pool[gid]
            old.times_used += 1
            if genome.times_succeeded > 0:
                old.times_succeeded += 1
            old.fitness_score = 0.7 * old.fitness_score + 0.3 * genome.fitness_score
        else:
            self.gene_pool[gid] = genome

    # ── 查询 ──

    @property
    def active_organisms(self) -> list[Organism]:
        return [o for o in self.organisms.values() if o.is_alive]

    @property
    def diversity(self) -> float:
        active = [o.genome for o in self.active_organisms if o.genome]
        if len(active) < 2:
            return 1.0
        total, n = 0.0, len(active)
        for i in range(n):
            for j in range(i + 1, n):
                total += active[i].genetic_distance(active[j])
        return total / (n * (n - 1) / 2)

    @property
    def total_revenue(self) -> float:
        return sum(o.total_earned for o in self.organisms.values())

    @property
    def total_costs(self) -> float:
        return sum(o.total_burned for o in self.organisms.values())

    # ── 报告 ──

    def report(self) -> str:
        active = self.active_organisms
        revenue = self.total_revenue
        costs = self.total_costs

        lines = [
            "═" * 56,
            "  AlphaX Hive Report",
            "═" * 56,
            f"  Active: {len(active)}  |  Dead: {len(self.dead_organisms)}  |  Gene Pool: {len(self.gene_pool)}",
            f"  Diversity: {self.diversity:.1%}  |  Net: ${revenue - costs:.0f}",
            "─" * 56,
        ]
        if active:
            lines.append(f"  {'TOP ACTIVE':<44} {'REV':>5} {'DAYS':>5}")
            for i, org in enumerate(
                sorted(active, key=lambda o: o.total_earned, reverse=True)[:5], 1
            ):
                name = org.genome.express() if org.genome else "unknown"
                lines.append(
                    f"  {i}. {name[:40]:<40} ${org.total_earned:>4.0f} {org.days_alive:>4}d"
                )
        return "\n".join(lines)

    # ── 持久化 ──

    def save(self) -> None:
        config.data_dir.mkdir(exist_ok=True)
        config.organisms_path.write_text(
            json.dumps({oid: org.to_dict() for oid, org in self.organisms.items()}, indent=2)
        )
        config.gene_pool_path.write_text(
            json.dumps({gid: g.to_dict() for gid, g in self.gene_pool.items()}, indent=2)
        )

    def load(self) -> bool:
        """加载持久化状态，返回是否成功加载了有意义的数据"""
        try:
            loaded_any = False
            if config.organisms_path.exists():
                raw = config.organisms_path.read_text().strip()
                if raw and raw != "{}":
                    self.organisms = {oid: Organism.from_dict(d) for oid, d in json.loads(raw).items()}
                    loaded_any = True
            if config.gene_pool_path.exists():
                raw = config.gene_pool_path.read_text().strip()
                if raw and raw != "{}":
                    self.gene_pool = {gid: Genome.from_dict(d) for gid, d in json.loads(raw).items()}
                    loaded_any = True
            return loaded_any
        except (json.JSONDecodeError, KeyError, OSError):
            return False
