"""AlphaX Alpha Brain — 智能决策编排器

编排 Policy → MCTS → Value 三阶段管道：

  Policy Network:  市场信号 → 20 个候选基因组
       ↓ top 5
  MCTS Engine:     三情景推演 → 最优基因
       ↓ best
  Hive.hatch():    孵化最优基因

同时维护"探索预算"——20% 随机探索防止过早收敛。
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field

from core.genome import Genome
from brain.policy_network import PolicyNetwork, Candidate
from brain.mcts_engine import MctsEngine, MctsResult
from brain.value_network import ValueNetwork, ValuePrediction
from brain.knowledge import KnowledgeEngine
from config import config

logger = logging.getLogger("alphax.alpha_brain")


@dataclass
class AlphaBrainDecision:
    """一次孵化决策的完整记录"""
    genome: Genome
    source: str               # "mcts" | "explore" | "inherit" | "seed"
    expected_revenue: float   # Value Network 预测
    survival_prob: float
    reasoning: str
    candidate_count: int      # 生成了多少候选
    mcts_confidence: float


@dataclass
class AlphaBrain:
    """编排 Policy → MCTS → Value 决策管道"""

    policy: PolicyNetwork = field(default_factory=PolicyNetwork)
    mcts: MctsEngine = field(default_factory=MctsEngine)
    value: ValueNetwork = field(default_factory=ValueNetwork)
    knowledge: KnowledgeEngine = field(default_factory=KnowledgeEngine)

    decision_history: list[AlphaBrainDecision] = field(default_factory=list)
    _api_failures: int = 0
    _api_cooldown_until: float = 0.0
    _dead_gene_fingerprints: set[str] = field(default_factory=set)

    def decide(
        self,
        gene_pool: dict[str, Genome],
        fund_balance: float,
        training_data: list[dict] | None = None,
        force_explore: bool = False,
    ) -> AlphaBrainDecision:
        """做出一个孵化决策：应该孵化什么基因？"""

        training = training_data or []

        # 20% 探索预算：随机尝试新基因
        if force_explore or (random.random() < config.exploration_budget):
            return self._explore_decision(gene_pool)

        # 有 API 就用完整管道（即使没有训练数据，LLM 也能推理）
        if config.deepseek_api_key:
            return self._full_pipeline(gene_pool, fund_balance, training)

        # 无 API：有数据用统计，没数据用启发式
        if len(training) >= 10:
            return self._full_pipeline(gene_pool, fund_balance, training)

        return self._heuristic_decision(gene_pool)

    def _full_pipeline(
        self,
        gene_pool: dict[str, Genome],
        fund_balance: float,
        training_data: list[dict],
    ) -> AlphaBrainDecision:
        """完整的三阶段决策管道，API 失败时自动降级"""

        # API 退避：连续失败超过阈值则跳过 LLM 调用
        if self._api_failures >= 3 and time.time() < self._api_cooldown_until:
            logger.warning(f"DeepSeek API cooldown ({self._api_failures} failures), falling back")
            return self._heuristic_decision(gene_pool)

        try:
            return self._run_full_pipeline(gene_pool, fund_balance, training_data)
        except Exception as e:
            self._api_failures += 1
            self._api_cooldown_until = time.time() + min(60 * self._api_failures, 600)
            logger.warning(f"DeepSeek API failed (failure #{self._api_failures}): {e}")
            return self._heuristic_decision(gene_pool)

    def _run_full_pipeline(
        self,
        gene_pool: dict[str, Genome],
        fund_balance: float,
        training_data: list[dict],
    ) -> AlphaBrainDecision:
        """实际执行三阶段管道"""

        # Stage 1: Policy Network — 生成候选
        candidates = self.policy.generate_candidates(
            gene_pool, fund_balance, count=20
        )

        # 选出 Top 5 送 MCTS
        top_candidates = self.policy.select_for_mcts(candidates, n=5)

        # Stage 2: MCTS — 深度推演
        mcts_results = self.mcts.evaluate(top_candidates, training_data)
        best_result = self.mcts.select_best(mcts_results)

        # Stage 3: Value Network — 最终预测（可选，已有 MCTS 预估）
        if best_result:
            # 用 Value Network 做交叉验证
            vn_pred = self.value.predict(
                best_result.genome, training_data,
                market_context={
                    "category": best_result.genome.category.value,
                    "survival_rate": best_result.survival_probability,
                    "competition": "medium",
                },
            )

            decision = AlphaBrainDecision(
                genome=best_result.genome,
                source="mcts",
                expected_revenue=vn_pred.predicted_monthly_revenue,
                survival_prob=best_result.survival_probability,
                reasoning=f"MCTS: {best_result.reasoning} | VN: {vn_pred.reasoning}",
                candidate_count=len(candidates),
                mcts_confidence=best_result.confidence,
            )
        else:
            decision = self._heuristic_decision(gene_pool)

        self.decision_history.append(decision)
        return decision

    def _explore_decision(self, gene_pool: dict[str, Genome]) -> AlphaBrainDecision:
        """探索模式：随机生成新基因组"""
        from core.genome import SEED_GENOMES
        from brain.policy_network import PolicyNetwork
        pn = PolicyNetwork()
        genome = pn._random_new_genome()

        decision = AlphaBrainDecision(
            genome=genome,
            source="explore",
            expected_revenue=genome.price_point * 10,
            survival_prob=0.4,
            reasoning="探索预算：随机尝试新基因组合",
            candidate_count=1,
            mcts_confidence=0.2,
        )
        self.decision_history.append(decision)
        return decision

    def _heuristic_decision(self, gene_pool: dict[str, Genome]) -> AlphaBrainDecision:
        """数据不足时的启发式决策，避开已知死亡基因模式"""
        from core.genome import SEED_GENOMES

        if gene_pool:
            ranked = sorted(
                gene_pool.values(),
                key=lambda g: (g.fitness_score, g.survival_rate),
                reverse=True,
            )
            # 避开最近决策中已失败的基因指纹
            for candidate in ranked:
                fp = f"{candidate.category.value}:{candidate.pricing_model.value}:{candidate.price_point:.0f}"
                if fp not in self._dead_gene_fingerprints:
                    genome = candidate.mutate()
                    break
            else:
                genome = ranked[0].mutate()
        else:
            genome = random.choice(SEED_GENOMES).mutate()

        decision = AlphaBrainDecision(
            genome=genome,
            source="inherit",
            expected_revenue=genome.price_point * 12,
            survival_prob=0.5,
            reasoning="数据不足，用启发式选择",
            candidate_count=1,
            mcts_confidence=0.1,
        )
        self.decision_history.append(decision)
        return decision

    # ── 学习：从结果中改进 ──

    def learn_from_outcome(
        self,
        decision: AlphaBrainDecision,
        actual_revenue: float,
        actual_survived: bool,
    ):
        """从实际结果学习，闭环改进"""
        pred = ValuePrediction(
            genome_id=decision.genome.genome_id,
            predicted_monthly_revenue=decision.expected_revenue,
            predicted_survival_prob=decision.survival_prob,
            confidence=decision.mcts_confidence,
            reasoning=decision.reasoning,
        )
        self.value.evaluate(pred, actual_revenue, actual_survived)

    @property
    def hit_rate(self) -> float:
        """决策命中率：预测存活且实际存活的占比"""
        if not self.value.accuracy_log:
            return 0.5
        correct = sum(1 for e in self.value.accuracy_log if e["survival_correct"])
        return correct / len(self.value.accuracy_log)

    def record_death(self, genome: Genome):
        """记录死亡基因指纹，避免启发式决策重复孵化类似基因"""
        if genome:
            fp = f"{genome.category.value}:{genome.pricing_model.value}:{genome.price_point:.0f}"
            self._dead_gene_fingerprints.add(fp)

    @property
    def summary(self) -> dict:
        return {
            "total_decisions": len(self.decision_history),
            "mcts_decisions": sum(1 for d in self.decision_history if d.source == "mcts"),
            "explore_decisions": sum(1 for d in self.decision_history if d.source == "explore"),
            "inherit_decisions": sum(1 for d in self.decision_history if d.source == "inherit"),
            "hit_rate": self.hit_rate,
            "mean_revenue_error": self.value.mean_revenue_error,
        }
