"""跨实例基因交换

不同 alphax 实例之间可以交换优秀基因。
类似细菌的水平基因转移——成功的基因片段可以跨越实例边界传播。
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class GeneCard:
    """一张基因卡片——可跨实例交换的成功基因摘要"""
    gene_id: str
    genome_summary: str
    product_type: str
    category: str
    price_point: float
    llm_backend: str
    fitness_score: float
    survival_rate: float
    total_earned: float
    days_alive: int
    source_instance: str = ""
    exported_at: str = ""
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.gene_id:
            raw = f"{self.genome_summary}{self.source_instance}{self.exported_at}"
            self.gene_id = hashlib.sha256(raw.encode()).hexdigest()[:12]
        if not self.exported_at:
            self.exported_at = datetime.now(timezone.utc).isoformat()


class GeneBank:
    """跨实例基因库

    导出：成功的 organism 的基因被序列化为 GeneCard
    导入：其他实例的 GeneCard 被注入到本地 gene_pool
    """

    def __init__(self, instance_id: str = ""):
        self._export_path = config.data_dir / "gene_export.json"
        self._import_path = config.data_dir / "gene_import.json"
        self.instance_id = instance_id or hashlib.sha256(
            str(Path(__file__).parent).encode()
        ).hexdigest()[:8]

        self.exported: list[GeneCard] = []
        self.imported: list[GeneCard] = []
        self._load()

    def export_gene(self, organism) -> GeneCard | None:
        """导出一个成功 organism 的基因"""
        if not organism.genome:
            return None

        genome = organism.genome
        if organism.total_earned <= 0 or organism.days_alive < 14:
            return None  # 只导出已验证成功的基因

        card = GeneCard(
            gene_id="",
            genome_summary=str(genome.express()) if hasattr(genome, 'express') else str(genome),
            product_type=str(getattr(genome, 'product_type', 'unknown')),
            category=str(getattr(genome, 'category', 'unknown')),
            price_point=getattr(genome, 'price_point', 0),
            llm_backend=getattr(genome, 'llm_backend', 'unknown') if hasattr(genome, 'llm_backend') else 'unknown',
            fitness_score=genome.fitness_score,
            survival_rate=organism.days_alive / max(1, organism.days_alive + organism.consecutive_loss_days),
            total_earned=organism.total_earned,
            days_alive=organism.days_alive,
            source_instance=self.instance_id,
        )
        self.exported.append(card)
        self._save()
        return card

    def import_gene(self, card: GeneCard) -> bool:
        """导入一个外部基因卡片"""
        # 检查是否已存在
        for existing in self.imported:
            if existing.gene_id == card.gene_id:
                return False
        self.imported.append(card)
        self._save()
        return True

    def get_import_candidates(self, category: str = "",
                              min_fitness: float = 0.3) -> list[GeneCard]:
        """获取可注入本地的导入基因"""
        candidates = self.imported
        if category:
            candidates = [c for c in candidates if c.category == category]
        return [c for c in candidates if c.fitness_score >= min_fitness]

    @property
    def top_exported(self) -> list[GeneCard]:
        return sorted(self.exported, key=lambda c: c.fitness_score, reverse=True)[:20]

    @property
    def summary(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "exported_count": len(self.exported),
            "imported_count": len(self.imported),
            "top_categories": list(set(c.category for c in self.exported[:20])),
        }

    def _save(self):
        try:
            data = {
                "instance_id": self.instance_id,
                "exported": [
                    {
                        "gene_id": c.gene_id,
                        "genome_summary": c.genome_summary,
                        "product_type": c.product_type,
                        "category": c.category,
                        "price_point": c.price_point,
                        "llm_backend": c.llm_backend,
                        "fitness_score": c.fitness_score,
                        "survival_rate": c.survival_rate,
                        "total_earned": c.total_earned,
                        "days_alive": c.days_alive,
                        "source_instance": c.source_instance,
                        "exported_at": c.exported_at,
                        "tags": c.tags,
                    }
                    for c in self.exported
                ],
                "imported": [
                    {
                        "gene_id": c.gene_id,
                        "genome_summary": c.genome_summary,
                        "product_type": c.product_type,
                        "category": c.category,
                        "price_point": c.price_point,
                        "llm_backend": c.llm_backend,
                        "fitness_score": c.fitness_score,
                        "survival_rate": c.survival_rate,
                        "total_earned": c.total_earned,
                        "days_alive": c.days_alive,
                        "source_instance": c.source_instance,
                        "exported_at": c.exported_at,
                        "tags": c.tags,
                    }
                    for c in self.imported
                ],
            }
            self._export_path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _load(self):
        if self._export_path.exists():
            try:
                data = json.loads(self._export_path.read_text())
                self.instance_id = data.get("instance_id", self.instance_id)
                for d in data.get("exported", []):
                    self.exported.append(GeneCard(**d))
                for d in data.get("imported", []):
                    self.imported.append(GeneCard(**d))
            except (json.JSONDecodeError, OSError):
                pass
