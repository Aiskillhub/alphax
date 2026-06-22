"""二阶元反思器

不止反思"市场怎么样"——反思"我之前的反思有没有用"。

追踪每条 Insight → 7 天后 fitness 变化 → 学习哪种 Insight 类型有效。
越反思越会反思。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class InsightTrace:
    """一条 Insight 的完整追踪"""
    insight_id: str
    insight_type: str        # strategy / rule_change / new_gene / tool_request / pattern
    insight_summary: str
    action_taken: str = ""   # 实际做了什么
    fitness_before: float = 0.0
    fitness_after: float = 0.0
    delta: float = 0.0       # fitness 变化
    was_effective: bool = False
    applied_at: str = ""
    evaluated_at: str = ""

    def __post_init__(self):
        if not self.applied_at:
            self.applied_at = datetime.now(timezone.utc).isoformat()


@dataclass
class MetaReflector:
    """二阶学习：追踪哪些改变真正带来了提升

    核心洞察：不是所有 Insight 都一样有效。
    有些类型的改变（如 '调整价格'）可能比其他的（如 '增加截图数量'）更有影响力。
    MetaReflector 学习这种模式。
    """

    _traces_path: Path = config.data_dir / "insight_traces.jsonl"
    _pending: dict[str, InsightTrace] = field(default_factory=dict)
    _completed: list[InsightTrace] = field(default_factory=list)
    _type_effectiveness: dict[str, list[float]] = field(default_factory=dict)

    def __post_init__(self):
        self._load()

    def track(self, insight, fitness_before: float) -> str:
        """记录一条 Insight 被应用时的状态"""
        trace = InsightTrace(
            insight_id=f"trace_{datetime.now(timezone.utc).timestamp()}",
            insight_type=insight.type if hasattr(insight, 'type') else 'unknown',
            insight_summary=insight.summary if hasattr(insight, 'summary') else str(insight)[:100],
            action_taken=insight.action if hasattr(insight, 'action') else '',
            fitness_before=fitness_before,
            fitness_after=fitness_before,  # 等 7 天后更新
        )
        self._pending[trace.insight_id] = trace
        return trace.insight_id

    def evaluate(self, current_fitness: float) -> list[InsightTrace]:
        """评估所有 pending traces，找出哪些变有效的"""
        matured = []
        now = datetime.now(timezone.utc)

        for tid, trace in list(self._pending.items()):
            applied_time = datetime.fromisoformat(trace.applied_at)
            days_elapsed = (now - applied_time).days

            if days_elapsed >= 7:
                trace.fitness_after = current_fitness
                trace.evaluated_at = now.isoformat()
                self._completed.append(trace)

                # 按类型聚合效果
                if trace.insight_type not in self._type_effectiveness:
                    self._type_effectiveness[trace.insight_type] = []
                self._type_effectiveness[trace.insight_type].append(trace.delta)

                matured.append(trace)
                del self._pending[tid]

        if matured:
            self._save()
        return matured

    @property
    def best_insight_types(self) -> list[tuple[str, float, int]]:
        """返回最有效的 Insight 类型排序"""
        ranked = []
        for itype, deltas in self._type_effectiveness.items():
            if len(deltas) >= 2:
                avg = sum(deltas) / len(deltas)
                ranked.append((itype, round(avg, 4), len(deltas)))
        return sorted(ranked, key=lambda x: x[1], reverse=True)

    @property
    def worst_insight_types(self) -> list[tuple[str, float, int]]:
        """返回最无效的 Insight 类型"""
        ranked = self.best_insight_types
        return list(reversed(ranked))

    def bias_reflection(self, base_prompt: str) -> str:
        """为 Reflector 的 prompt 添加二阶学习偏向

        告诉 LLM 过去哪种建议有效，让它偏向生成更多这类建议。
        """
        if not self.best_insight_types:
            return base_prompt

        lines = [base_prompt, "", "## Meta-Learning: What Has Worked Historically"]

        best = self.best_insight_types[:3]
        worst = self.worst_insight_types[:2]

        if best:
            lines.append("Most effective insight types (average fitness improvement):")
            for itype, avg, count in best:
                lines.append(f"  - {itype}: +{avg:.3f} fitness (n={count})")

        if worst:
            lines.append("Least effective insight types:")
            for itype, avg, count in worst:
                lines.append(f"  - {itype}: {avg:.3f} fitness (n={count})")

        lines.append("\nBias your suggestions toward the most effective types.")
        return "\n".join(lines)

    @property
    def summary(self) -> dict:
        return {
            "pending_traces": len(self._pending),
            "completed_traces": len(self._completed),
            "best_types": [t[0] for t in self.best_insight_types[:3]],
            "overall_effectiveness": round(
                sum(1 for t in self._completed if t.was_effective) / max(1, len(self._completed)), 2
            ),
        }

    def _save(self):
        try:
            with open(self._traces_path, "w") as f:
                for t in self._completed:
                    f.write(json.dumps({
                        "insight_id": t.insight_id,
                        "insight_type": t.insight_type,
                        "insight_summary": t.insight_summary,
                        "action_taken": t.action_taken,
                        "fitness_before": t.fitness_before,
                        "fitness_after": t.fitness_after,
                        "delta": t.delta,
                        "was_effective": t.was_effective,
                        "applied_at": t.applied_at,
                        "evaluated_at": t.evaluated_at,
                    }) + "\n")
        except OSError:
            pass

    def _load(self):
        if self._traces_path.exists():
            try:
                for line in self._traces_path.read_text().strip().split("\n"):
                    if line:
                        d = json.loads(line)
                        t = InsightTrace(**d)
                        self._completed.append(t)
                        if t.insight_type not in self._type_effectiveness:
                            self._type_effectiveness[t.insight_type] = []
                        self._type_effectiveness[t.insight_type].append(t.delta)
            except (json.JSONDecodeError, OSError):
                pass
