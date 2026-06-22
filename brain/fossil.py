"""化石记录

每个死掉的 organism 留下记录：什么策略、活了多久、为什么死。
后来者在决定基因时可以参考这些化石。
失败不是浪费——是数据。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class FossilRecord:
    """一个死亡 organism 的化石"""
    organism_id: str
    genome_summary: str          # 基因策略简述
    product_type: str
    category: str
    price_point: float
    llm_backend: str
    days_alive: int
    total_earned: float
    total_burned: float
    death_cause: str             # energy_depleted / consecutive_loss / manual_kill
    lessons: list[str] = field(default_factory=list)
    died_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def was_profitable(self) -> bool:
        return self.total_earned > self.total_burned

    @property
    def roi(self) -> float:
        if self.total_burned == 0:
            return 0.0
        return (self.total_earned - self.total_burned) / self.total_burned


class FossilDB:
    """化石数据库——死 organism 的集体记忆"""

    def __init__(self):
        self._path = config.data_dir / "fossils.jsonl"
        self._index_path = config.data_dir / "fossils_index.json"
        self.records: list[FossilRecord] = []
        self._load()

    def bury(self, organism) -> FossilRecord:
        """埋葬一个死亡的 organism，提取化石"""
        genome = organism.genome
        death_cause = "unknown"
        if organism.consecutive_loss_days >= config.survival_threshold_days:
            death_cause = "consecutive_loss"
        elif organism.energy <= 0:
            death_cause = "energy_depleted"
        elif organism.state.value == "dead":
            death_cause = "natural_death"

        # 提取教训
        lessons = []
        if organism.days_alive < config.breed_min_days:
            lessons.append(f"Did not survive to breeding age ({organism.days_alive}d < {config.breed_min_days}d)")
        if organism.total_earned < organism.total_burned:
            lessons.append(f"Never profitable: earned ${organism.total_earned:.2f}, burned ${organism.total_burned:.2f}")
        if genome and hasattr(genome, 'price_point'):
            if organism.total_downloads == 0:
                lessons.append(f"No downloads at ${genome.price_point:.2f} — price too high or no demand")

        record = FossilRecord(
            organism_id=organism.organism_id,
            genome_summary=str(genome.express()) if genome and hasattr(genome, 'express') else "unknown",
            product_type=str(getattr(genome, 'product_type', 'unknown')) if genome else "unknown",
            category=str(getattr(genome, 'category', 'unknown')) if genome else "unknown",
            price_point=getattr(genome, 'price_point', 0) if genome else 0,
            llm_backend=getattr(genome, 'llm_backend', 'deepseek') if genome and hasattr(genome, 'llm_backend') else "unknown",
            days_alive=organism.days_alive,
            total_earned=organism.total_earned,
            total_burned=organism.total_burned,
            death_cause=death_cause,
            lessons=lessons,
            died_at=organism.died_at or datetime.now(timezone.utc).isoformat(),
        )
        self.records.append(record)
        self._save(record)
        return record

    def get_lessons(self, category: str = "", limit: int = 10) -> list[str]:
        """获取某个品类的历史教训"""
        lessons = []
        for r in self.records:
            if category and r.category != category:
                continue
            lessons.extend(r.lessons)
        return lessons[:limit]

    def category_survival_rate(self, category: str) -> float:
        """某品类的存活率（盈利的占比）"""
        matches = [r for r in self.records if r.category == category]
        if not matches:
            return 0.5
        profitable = sum(1 for r in matches if r.was_profitable)
        return profitable / len(matches)

    def category_avg_roi(self, category: str) -> float:
        """某品类平均 ROI"""
        matches = [r for r in self.records if r.category == category]
        if not matches:
            return 0.0
        return sum(r.roi for r in matches) / len(matches)

    def deadliest_price_range(self) -> tuple[float, float]:
        """找到死亡率最高的价格区间"""
        if not self.records:
            return (0, 0)
        prices = [r.price_point for r in self.records]
        return (min(prices), max(prices))

    @property
    def recent_losses(self) -> list[dict]:
        """最近 10 个化石的摘要"""
        return [
            {
                "organism_id": r.organism_id,
                "days_alive": r.days_alive,
                "death_cause": r.death_cause,
                "genome_summary": r.genome_summary,
                "roi": round(r.roi, 2),
            }
            for r in sorted(self.records, key=lambda x: x.died_at, reverse=True)[:10]
        ]

    def _save(self, record: FossilRecord):
        try:
            entry = {
                "organism_id": record.organism_id,
                "genome_summary": record.genome_summary,
                "product_type": record.product_type,
                "category": record.category,
                "price_point": record.price_point,
                "llm_backend": record.llm_backend,
                "days_alive": record.days_alive,
                "total_earned": record.total_earned,
                "total_burned": record.total_burned,
                "death_cause": record.death_cause,
                "lessons": record.lessons,
                "died_at": record.died_at,
            }
            with open(self._path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    def _load(self):
        if self._path.exists():
            try:
                for line in self._path.read_text().strip().split("\n"):
                    if line:
                        d = json.loads(line)
                        self.records.append(FossilRecord(
                            organism_id=d.get("organism_id", ""),
                            genome_summary=d.get("genome_summary", ""),
                            product_type=d.get("product_type", ""),
                            category=d.get("category", ""),
                            price_point=d.get("price_point", 0),
                            llm_backend=d.get("llm_backend", ""),
                            days_alive=d.get("days_alive", 0),
                            total_earned=d.get("total_earned", 0),
                            total_burned=d.get("total_burned", 0),
                            death_cause=d.get("death_cause", ""),
                            lessons=d.get("lessons", []),
                            died_at=d.get("died_at", ""),
                        ))
            except (json.JSONDecodeError, OSError):
                pass

    @property
    def count(self) -> int:
        return len(self.records)

    @property
    def summary(self) -> dict:
        if not self.records:
            return {"total": 0}
        return {
            "total": len(self.records),
            "profitable": sum(1 for r in self.records if r.was_profitable),
            "avg_days_alive": round(sum(r.days_alive for r in self.records) / len(self.records), 1),
            "top_death_causes": list(set(r.death_cause for r in self.records)),
            "categories": list(set(r.category for r in self.records)),
        }
