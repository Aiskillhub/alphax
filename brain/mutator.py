"""变异执行器

将 Reflector 生成的 Insight 转化为实际改变：
- 新增/删除基因位点
- 调整变异率、选择压力
- 注册工具需求
- 更新 fitness 函数权重
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from brain.reflector import Insight
from config import config


@dataclass
class MutationLog:
    """一次规则变异的记录"""
    timestamp: str
    insight_summary: str
    what_changed: str
    old_value: str
    new_value: str


@dataclass
class Mutator:
    """应用洞察，改变系统自身规则"""

    _log_path: Path = config.data_dir / "mutation_log.jsonl"
    _history: list[MutationLog] = field(default_factory=list)

    def apply(self, insights: list[Insight], gene_pool=None) -> list[MutationLog]:
        """应用洞察，返回实际执行的变异"""
        results = []
        for ins in insights:
            if ins.confidence < 0.5:
                continue

            if ins.type == "new_gene":
                result = self._add_gene_locus(ins, gene_pool)
            elif ins.type == "rule_change":
                result = self._change_rule(ins)
            elif ins.type == "tool_request":
                result = self._register_tool_request(ins)
            elif ins.type == "strategy":
                result = self._record_strategy(ins)
            else:
                result = self._record_pattern(ins)

            if result:
                results.append(result)

        self._history.extend(results)
        self._save(results)
        return results

    def _add_gene_locus(self, ins: Insight, gene_pool) -> MutationLog | None:
        """在基因空间中添加新位点"""
        # 这会通过 gene_pool.add_gene_locus() 实现
        # 这里记录日志
        log = MutationLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            insight_summary=ins.summary,
            what_changed="new_gene_locus",
            old_value="",
            new_value=ins.action,
        )
        # 如果 gene_pool 可用，实际添加位点
        if gene_pool and hasattr(gene_pool, 'add_gene_locus'):
            gene_pool.add_gene_locus(ins.action, ins.detail)
        return log

    def _change_rule(self, ins: Insight) -> MutationLog:
        """改变进化规则参数"""
        action = ins.action.lower()

        if "exploration" in action:
            old = config.exploration_budget
            if "increase" in action:
                config.exploration_budget = min(0.5, old * 1.5)
            elif "decrease" in action:
                config.exploration_budget = max(0.05, old * 0.7)
            return MutationLog(
                timestamp=datetime.now(timezone.utc).isoformat(),
                insight_summary=ins.summary,
                what_changed="exploration_budget",
                old_value=str(old),
                new_value=str(config.exploration_budget),
            )

        if "mutation" in action and "rate" in action:
            old = config.mutation_rate
            if "increase" in action:
                config.mutation_rate = min(0.3, old * 1.5)
            elif "decrease" in action:
                config.mutation_rate = max(0.02, old * 0.7)
            return MutationLog(
                timestamp=datetime.now(timezone.utc).isoformat(),
                insight_summary=ins.summary,
                what_changed="mutation_rate",
                old_value=str(old),
                new_value=str(config.mutation_rate),
            )

        if "survival" in action or "threshold" in action:
            old = config.survival_threshold_days
            if "reduce" in action or "tighten" in action:
                config.survival_threshold_days = max(3, old - 2)
            elif "increase" in action:
                config.survival_threshold_days = min(14, old + 2)
            return MutationLog(
                timestamp=datetime.now(timezone.utc).isoformat(),
                insight_summary=ins.summary,
                what_changed="survival_threshold_days",
                old_value=str(old),
                new_value=str(config.survival_threshold_days),
            )

        return MutationLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            insight_summary=ins.summary,
            what_changed="rule_change",
            old_value="",
            new_value=ins.action,
        )

    def _register_tool_request(self, ins: Insight) -> MutationLog:
        """注册一个新工具需求"""
        from pathlib import Path
        toolkit_path = config.data_dir / "tool_requests.json"
        try:
            existing = json.loads(toolkit_path.read_text()) if toolkit_path.exists() else []
        except (json.JSONDecodeError, OSError):
            existing = []
        existing.append({
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "summary": ins.summary,
            "detail": ins.detail,
            "action": ins.action,
            "built": False,
        })
        toolkit_path.write_text(json.dumps(existing, indent=2))
        return MutationLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            insight_summary=ins.summary,
            what_changed="tool_request",
            old_value="",
            new_value=ins.action,
        )

    def _record_strategy(self, ins: Insight) -> MutationLog:
        return MutationLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            insight_summary=ins.summary,
            what_changed="strategy",
            old_value="",
            new_value=ins.action,
        )

    def _record_pattern(self, ins: Insight) -> MutationLog:
        return MutationLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            insight_summary=ins.summary,
            what_changed="pattern",
            old_value="",
            new_value=ins.action,
        )

    def _save(self, results: list[MutationLog]):
        try:
            with open(self._log_path, "a") as f:
                for r in results:
                    f.write(json.dumps({
                        "timestamp": r.timestamp,
                        "insight": r.insight_summary,
                        "what": r.what_changed,
                        "old": r.old_value,
                        "new": r.new_value,
                    }) + "\n")
        except OSError:
            pass

    @property
    def recent_mutations(self) -> list[MutationLog]:
        return self._history[-20:]
