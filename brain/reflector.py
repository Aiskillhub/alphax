"""LLM 反思引擎

读 ObservationLog，总结模式，提议改进。
这是进化的"大脑"——看到现象，形成洞察，指导行动。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class Insight:
    """一条从观察中提炼的洞察"""
    type: str           # pattern / new_gene / rule_change / tool_request / strategy
    summary: str        # 一句话总结
    detail: str         # 详细解释
    confidence: float   # 0.0-1.0
    evidence: str       # 支持该洞察的证据
    action: str         # 建议采取的行动
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Reflector:
    """LLM 驱动的观察反思器

    定期读取 ObservationLog，用 LLM 分析趋势，生成 actionable 洞察。
    """

    model: str = "deepseek-chat"
    min_confidence: float = 0.5
    _cache_path: Path = config.data_dir / "insights.jsonl"

    def think(self, recent_logs: list[dict], fossils: list[dict] = None,
              gene_pool_stats: dict = None) -> list[Insight]:
        """主入口：分析最近日志，生成洞察列表

        Args:
            recent_logs: 最近 N 天的 ObservationLog 摘要
            fossils: 死亡 organism 的化石记录
            gene_pool_stats: 基因池统计（品类分布、fitness 分布等）
        """
        if not config.deepseek_api_key:
            return self._rule_based_insights(recent_logs, gene_pool_stats)

        prompt = self._build_reflection_prompt(recent_logs, fossils, gene_pool_stats)
        try:
            insights = self._call_llm(prompt)
            self._save(insights)
            return insights
        except Exception:
            return self._rule_based_insights(recent_logs, gene_pool_stats)

    def _build_reflection_prompt(self, logs: list[dict], fossils: list[dict] | None,
                                 stats: dict | None) -> str:
        """构建反思 prompt"""
        lines = [
            "You are the reflection engine of an autonomous AI evolution system.",
            "Your job: analyze recent observations and propose improvements.",
            "",
            "## Recent Observations",
        ]
        for log in logs[-7:]:  # 最近 7 天
            if isinstance(log, dict):
                ts = str(log.get('timestamp', '?'))[:10]
                mkt = log.get('market_count', 0)
                pop = log.get('self_count', 0)
                cats = log.get('market_categories', [])
            else:
                ts = str(getattr(log, 'timestamp', '?'))[:10]
                mkt = len(getattr(log, 'market_signals', []))
                pop = len(getattr(log, 'self_signals', []))
                cats = list(set(s.category for s in getattr(log, 'market_signals', [])))
            lines.append(f"- {ts}: market={mkt} signals, "
                         f"population={pop} organisms, "
                         f"categories={cats}")

        if stats:
            lines.extend([
                "",
                "## Gene Pool Statistics",
                f"Total genomes: {stats.get('total_genomes', stats.get('total', 0))}",
                f"Categories: {stats.get('categories', [])}",
                f"Diversity: {stats.get('diversity', 0)}",
            ])

        if fossils:
            lines.extend([
                "",
                "## Recent Deaths (Fossil Records)",
            ])
            for f in fossils[-5:]:
                lines.append(
                    f"- {f.get('organism_id', '?')[:8]}: "
                    f"lived {f.get('days_alive', 0)}d, "
                    f"cause={f.get('death_cause', '?')}, "
                    f"genome={f.get('genome_summary', '?')}"
                )

        lines.extend([
            "",
            "## Your Task",
            "Analyze the data and propose up to 5 actionable insights. For each, provide:",
            "1. TYPE: pattern / new_gene / rule_change / tool_request / strategy",
            "2. SUMMARY: one sentence",
            "3. DETAIL: 2-3 sentences explaining the reasoning",
            "4. CONFIDENCE: 0.0-1.0 (how sure are you?)",
            "5. EVIDENCE: what data supports this?",
            "6. ACTION: what should the system do?",
            "",
            "Be specific. Propose new gene loci if you see patterns not captured by existing genes.",
            "Suggest rule changes if mutation rates or selection criteria need adjustment.",
            "Request new tools if you see repetitive manual work that could be automated.",
            "",
            "Format as JSON array: [{\"type\":\"...\",\"summary\":\"...\",\"detail\":\"...\",\"confidence\":0.X,\"evidence\":\"...\",\"action\":\"...\"}]",
        ])
        return "\n".join(lines)

    def _call_llm(self, prompt: str) -> list[Insight]:
        """调用 LLM 进行反思"""
        import urllib.request

        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You analyze data and propose actionable improvements. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 2000,
        }).encode()

        req = urllib.request.Request(
            f"{config.deepseek_base_url}/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {config.deepseek_api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())

        content = data["choices"][0]["message"]["content"]
        # Extract JSON from response — try multiple strategies
        candidates = []
        candidates.append(content.strip())
        if "```json" in content:
            block = content.split("```json", 1)[1]
            if "```" in block:
                candidates.append(block.split("```", 1)[0].strip())
        if "```" in content:
            parts = content.split("```")
            for i in range(1, len(parts), 2):
                candidates.append(parts[i].strip())
        start = content.find("[")
        end = content.rfind("]") + 1
        if start >= 0 and end > start:
            candidates.append(content[start:end])

        items = None
        last_err = None
        for raw in candidates:
            if not raw or not (raw.startswith("[") or raw.startswith("{")):
                continue
            try:
                items = json.loads(raw)
                break
            except json.JSONDecodeError as e:
                last_err = e
                try:
                    from brain.creator import Creator
                    items = json.loads(Creator._repair_json(raw))
                    break
                except json.JSONDecodeError:
                    continue

        if items is None:
            raise RuntimeError(f"Reflector JSON parse failed: {last_err}")

        return [
            Insight(
                type=item.get("type", "pattern"),
                summary=item.get("summary", ""),
                detail=item.get("detail", ""),
                confidence=float(item.get("confidence", 0.5)),
                evidence=item.get("evidence", ""),
                action=item.get("action", ""),
            )
            for item in items
            if item.get("confidence", 0) >= self.min_confidence
        ]

    def _rule_based_insights(self, logs: list[dict], stats: dict | None) -> list[Insight]:
        """无 LLM 时的规则折回——基础模式识别"""
        insights = []

        # 检查市场趋势
        categories = []
        for log in logs[-3:]:
            if isinstance(log, dict):
                categories.extend(log.get("market_categories", []))
            else:
                for s in getattr(log, 'market_signals', []):
                    categories.append(getattr(s, 'category', 'unknown'))
        if categories:
            from collections import Counter
            top = Counter(categories).most_common(1)[0]
            insights.append(Insight(
                type="pattern",
                summary=f"Trending category: {top[0]} ({top[1]}x in 3 days)",
                detail=f"Market signals show growing interest in {top[0]}.",
                confidence=min(0.7, top[1] / 5),
                evidence=f"{top[1]} occurrences in recent logs",
                action=f"Increase {top[0]} product allocation by 20%",
            ))

        # 检查基因池健康度
        if stats:
            if stats.get("total", 0) < 10:
                insights.append(Insight(
                    type="rule_change",
                    summary="Gene pool is small — increase exploration",
                    detail=f"Only {stats['total']} genomes. Need more diversity.",
                    confidence=0.8,
                    evidence=f"Population: {stats['total']}",
                    action="Increase exploration budget from 20% to 40%",
                ))
            if stats.get("avg_fitness", 0) < 0.3:
                insights.append(Insight(
                    type="rule_change",
                    summary="Low average fitness — tighten selection",
                    detail="Most genomes are underperforming. Increase selection pressure.",
                    confidence=0.7,
                    evidence=f"Average fitness: {stats['avg_fitness']:.3f}",
                    action="Reduce survival threshold to remove bottom 40%",
                ))

        return insights

    def _save(self, insights: list[Insight]):
        try:
            with open(self._cache_path, "a") as f:
                for ins in insights:
                    f.write(json.dumps({
                        "type": ins.type, "summary": ins.summary,
                        "detail": ins.detail, "confidence": ins.confidence,
                        "evidence": ins.evidence, "action": ins.action,
                        "timestamp": ins.timestamp,
                    }) + "\n")
        except OSError:
            pass
