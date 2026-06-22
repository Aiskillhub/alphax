"""AlphaX MCTS Engine — 蒙特卡洛树搜索市场推演

对 Policy Network 选出的 Top 5 候选基因组做深度推演。

MCTS 四阶段：
  1. Selection: 从候选中选择最有潜力的
  2. Expansion: 对选中基因组做市场情景展开（乐观/中性/悲观）
  3. Simulation: 用 Value Network 预测每种情景的收益
  4. Backpropagation: 更新节点统计，选出最优

推演考虑维度：
  - 市场规模 & 增长趋势
  - 竞品反应（是否降价？）
  - 用户获取成本
  - 维护成本
  - Chrome Store 政策风险
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.genome import Genome
from core.api_utils import call_deepseek, extract_json
from brain.policy_network import Candidate
from config import config


@dataclass
class ScenarioNode:
    """MCTS 节点——一个市场情景"""
    genome: Genome
    scenario: str       # "optimistic" | "neutral" | "pessimistic"
    visits: int = 0
    total_value: float = 0.0  # 累计收益
    children: list[ScenarioNode] = field(default_factory=list)
    parent: ScenarioNode | None = None

    @property
    def avg_value(self) -> float:
        if self.visits == 0:
            return 0.0
        return self.total_value / self.visits

    def ucb_score(self, parent_visits: int, exploration: float = 1.4) -> float:
        """UCB1 公式"""
        if self.visits == 0:
            return float("inf")
        return self.avg_value + exploration * math.sqrt(
            math.log(parent_visits) / self.visits
        )


@dataclass
class MctsResult:
    genome: Genome
    expected_monthly_revenue: float
    survival_probability: float
    best_scenario: str
    worst_case_revenue: float
    reasoning: str  # DeepSeek 推理
    confidence: float


@dataclass
class MctsEngine:
    """市场推演引擎"""

    results: list[MctsResult] = field(default_factory=list)

    def evaluate(self, candidates: list[Candidate],
                 training_data: list[dict] | None = None) -> list[MctsResult]:
        """对候选基因组做深度推演，返回排序结果"""
        results = []
        for candidate in candidates:
            result = self._evaluate_one(candidate.genome, training_data or [])
            results.append(result)

        results.sort(key=lambda r: r.expected_monthly_revenue * r.survival_probability,
                     reverse=True)
        self.results = results
        return results

    def _evaluate_one(self, genome: Genome, training_data: list[dict]) -> MctsResult:
        """对一个基因组做 MCTS 推演"""
        if config.deepseek_api_key and training_data:
            return self._llm_evaluate(genome, training_data)
        return self._heuristic_evaluate(genome)

    def _llm_evaluate(self, genome: Genome, training_data: list[dict]) -> MctsResult:
        """用 DeepSeek API 做深度市场推演"""
        # 构建市场数据摘要
        survived = [s for s in training_data if s.get("survived")]
        survival_rate = len(survived) / len(training_data) if training_data else 0.5
        avg_revenue = (
            sum(s.get("total_earned", 0) for s in survived) / len(survived)
            if survived else 0
        )

        prompt = f"""你是一个市场策略顾问。对一个即将投放的数字产品做深度推演。

产品:
- 名称: {genome.express()}
- 品类: {genome.category.value}
- 定价: ${genome.price_point:.2f} ({genome.pricing_model.value})
- 目标: {genome.target_market.value}
- 复杂度: {genome.code_complexity}

历史参考:
- 品类存活率: {survival_rate:.0%}
- 品类平均收入: ${avg_revenue:.0f}
- 历史样本: {len(training_data)} 个

请推演三种情景，返回 JSON:
{{
  "optimistic": {{ "revenue": 数字, "probability": 0-1, "condition": "什么条件会实现这个情景" }},
  "neutral": {{ "revenue": 数字, "probability": 0-1, "condition": "..." }},
  "pessimistic": {{ "revenue": 数字, "probability": 0-1, "condition": "..." }},
  "overall_assessment": "综合评估（1-2句话，英文）",
  "risk_factors": ["风险1", "风险2"],
  "moat_sources": ["护城河1", "护城河2"]
}}

概率之和应为 1。收入为 30 天预期美元收入。
只返回 JSON，不要其他内容。"""

        try:
            content = call_deepseek(
                prompt, config.deepseek_api_key, config.deepseek_base_url,
                temperature=0.3, max_tokens=500,
            )
            content = extract_json(content)
            parsed = json.loads(content)

            # 加权计算
            optimistic = parsed.get("optimistic", {})
            neutral = parsed.get("neutral", {})
            pessimistic = parsed.get("pessimistic", {})

            opt_rev = optimistic.get("revenue", 100)
            opt_prob = optimistic.get("probability", 0.25)
            neu_rev = neutral.get("revenue", 50)
            neu_prob = neutral.get("probability", 0.50)
            pes_rev = pessimistic.get("revenue", 10)
            pes_prob = pessimistic.get("probability", 0.25)

            # 归一化概率
            total_p = opt_prob + neu_prob + pes_prob
            if total_p > 0:
                opt_prob /= total_p
                neu_prob /= total_p
                pes_prob /= total_p

            expected_revenue = opt_rev * opt_prob + neu_rev * neu_prob + pes_rev * pes_prob

            return MctsResult(
                genome=genome,
                expected_monthly_revenue=round(expected_revenue, 2),
                survival_probability=round(opt_prob + neu_prob, 2),
                best_scenario="optimistic",
                worst_case_revenue=round(pes_rev, 2),
                reasoning=parsed.get("overall_assessment", ""),
                confidence=0.6,
            )

        except Exception:
            return self._heuristic_evaluate(genome)

    def _heuristic_evaluate(self, genome: Genome) -> MctsResult:
        """启发式推演（无 API 时的简单模拟）"""
        # 基于价格估算转化
        price_factor = max(0.3, 1.0 - (genome.price_point - 3.99) / 15)
        base_revenue = genome.price_point * 15  # 假设 15 个用户

        # 三个情景
        opt_revenue = base_revenue * price_factor * 1.5
        neu_revenue = base_revenue * price_factor * 1.0
        pes_revenue = base_revenue * price_factor * 0.3

        # 复杂度影响存活率
        complexity_factor = {"minimal": 1.0, "standard": 0.85, "rich": 0.65}
        survival = 0.7 * complexity_factor.get(genome.code_complexity, 0.85)

        expected = opt_revenue * 0.25 + neu_revenue * 0.5 + pes_revenue * 0.25

        return MctsResult(
            genome=genome,
            expected_monthly_revenue=round(expected, 2),
            survival_probability=round(survival, 2),
            best_scenario="optimistic",
            worst_case_revenue=round(pes_revenue, 2),
            reasoning=f"启发式推演: 价格${genome.price_point} × 复杂度{genome.code_complexity}",
            confidence=0.3,
        )

    def select_best(self, results: list[MctsResult] | None = None) -> MctsResult | None:
        """选出综合评分最高的基因组"""
        items = results or self.results
        if not items:
            return None

        # 评分 = 预期收入 × 存活概率 × (1 - 变异系数)
        best = max(items, key=lambda r: r.expected_monthly_revenue * r.survival_probability)
        return best

    def best_genome(self) -> Genome | None:
        """返回最优基因组，供 Hive.hatch() 直接使用"""
        best = self.select_best()
        return best.genome if best else None
