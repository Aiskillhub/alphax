"""AlphaX Evolution — 变异记忆库 & 血统追踪

进化引擎的"经验"：记住哪些变异有效，偏向成功基因。

血统追踪：
  Genome.ancestors → [parent_id, grandparent_id, ...]
  记录完整的进化链

智能变异：
  MutationMemory → 记录每次变异的 fitness 变化
  下次变异时，偏向历史证明有效的方向
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class MutationRecord:
    """一次变异的历史记录"""
    genome_id: str
    parent_id: str
    field: str               # 哪个基因位点
    old_value: str
    new_value: str
    fitness_before: float
    fitness_after: float
    generation: int
    product_type: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MutationMemory:
    """变异知识库：什么变异在什么情况下有效"""

    def __init__(self):
        self._path = config.data_dir / "mutation_memory.json"
        self._records: list[MutationRecord] = []
        self._stats: dict[str, dict] = {}  # field → {total, success, avg_delta}
        self._load()

    def record(self, record: MutationRecord):
        """记录一次变异的结果。"""
        self._records.append(record)
        # 更新统计
        key = f"{record.field}|{record.product_type}"
        if key not in self._stats:
            self._stats[key] = {"total": 0, "success": 0, "avg_delta": 0.0}
        s = self._stats[key]
        s["total"] += 1
        delta = record.fitness_after - record.fitness_before
        if delta > 0:
            s["success"] += 1
        s["avg_delta"] = (s["avg_delta"] * (s["total"] - 1) + delta) / s["total"]
        self._save()

    def smart_rate(self, field: str, product_type: str = "any") -> float:
        """返回某个基因位点的智能变异率。

        历史成功率高的位点 → 更高的变异概率。
        从未变过的位点 → 默认概率。
        """
        base_rate = config.mutation_rate  # 0.10

        specific_key = f"{field}|{product_type}"
        any_key = f"{field}|any"

        for key in [specific_key, any_key]:
            if key in self._stats:
                s = self._stats[key]
                if s["total"] < 5:
                    continue
                success_rate = s["success"] / max(s["total"], 1)
                # 成功率 > 50% → 提高变异率；< 20% → 降低
                if success_rate > 0.5:
                    return min(0.35, base_rate * (1 + success_rate))
                elif success_rate < 0.2:
                    return max(0.03, base_rate * 0.5)

        return base_rate

    def suggest_direction(self, field: str, product_type: str = "any") -> str | None:
        """建议变异方向，基于历史成功案例。

        Returns:
            "increase" / "decrease" / "change" / None（随机）
        """
        specific_key = f"{field}|{product_type}"
        records = [r for r in self._records
                   if r.field == field and r.fitness_after > r.fitness_before]

        if not records:
            return None

        # 看成功案例中，是增大还是减小更多
        increased = 0
        decreased = 0
        for r in records:
            try:
                old_f = float(r.old_value)
                new_f = float(r.new_value)
                if new_f > old_f:
                    increased += 1
                elif new_f < old_f:
                    decreased += 1
            except (ValueError, TypeError):
                return "change"

        if increased > decreased * 2:
            return "increase"
        elif decreased > increased * 2:
            return "decrease"
        return "change"

    def top_fields(self, n: int = 5) -> list[tuple[str, float]]:
        """返回最有改进效果的基因位点。"""
        scored = []
        for key, s in self._stats.items():
            if s["total"] >= 3:
                scored.append((key, s["avg_delta"]))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:n]

    def report(self) -> str:
        """生成变异知识库报告。"""
        lines = ["🧬 变异知识库报告", "═" * 40]
        lines.append(f"总记录: {len(self._records)} 次变异")
        lines.append(f"追踪字段: {len(self._stats)} 个")
        lines.append("")
        lines.append("最佳改进方向:")
        for i, (key, delta) in enumerate(self.top_fields(5), 1):
            field, ptype = key.split("|", 1)
            s = self._stats[key]
            lines.append(f"  {i}. {field} ({ptype}) → 平均提升 {delta:+.1f} ({s['success']}/{s['total']}次成功)")
        return "\n".join(lines)

    def _save(self):
        try:
            data = {
                "records": [r.__dict__ for r in self._records[-500:]],  # 只保留最近 500 条
                "stats": self._stats,
            }
            self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception:
            pass

    def _load(self):
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text())
                self._records = [MutationRecord(**r) for r in data.get("records", [])]
                self._stats = data.get("stats", {})
        except Exception:
            pass


# ── 血统追踪 ──

class Lineage:
    """血统管理器：追踪基因组进化树"""

    def __init__(self):
        self._path = config.data_dir / "lineage.json"
        self._tree: dict[str, dict] = {}  # genome_id → {parent, children, fitness, gen}

    def register(self, genome_id: str, parent_id: str = "",
                 fitness: float = 0.0, generation: int = 0):
        """注册一个基因及其父系。"""
        self._tree[genome_id] = {
            "parent": parent_id,
            "children": [],
            "fitness": fitness,
            "generation": generation,
        }
        if parent_id and parent_id in self._tree:
            self._tree[parent_id]["children"].append(genome_id)
        self._save()

    def ancestors(self, genome_id: str, max_depth: int = 10) -> list[str]:
        """返回一个基因的完整祖先链。"""
        chain = []
        current = genome_id
        for _ in range(max_depth):
            node = self._tree.get(current)
            if not node or not node["parent"]:
                break
            chain.append(node["parent"])
            current = node["parent"]
        return chain

    def descendants(self, genome_id: str) -> list[str]:
        """返回一个基因的所有后代。"""
        result = []
        stack = [genome_id]
        while stack:
            gid = stack.pop()
            node = self._tree.get(gid)
            if node:
                for child in node["children"]:
                    result.append(child)
                    stack.append(child)
        return result

    def dynasty_report(self, genome_id: str) -> str:
        """一个家族的报告。"""
        ancestors = self.ancestors(genome_id)
        descendants = self.descendants(genome_id)
        node = self._tree.get(genome_id, {})
        lines = [
            f"🧬 血统: {genome_id[:8]}",
            f"   代数: {node.get('generation', '?')}",
            f"   适应度: {node.get('fitness', 0):.1f}",
            f"   祖先: {len(ancestors)} 代 → {' → '.join(a[:8] for a in ancestors[:5])}",
            f"   后代: {len(descendants)} 个",
        ]
        return "\n".join(lines)

    def _save(self):
        try:
            self._path.write_text(json.dumps(self._tree, indent=2))
        except Exception:
            pass


# ── 全局实例 ──

mutation_memory = MutationMemory()
lineage = Lineage()
