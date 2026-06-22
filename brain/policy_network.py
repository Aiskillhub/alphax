"""AlphaX Policy Network — 市场信号 → 候选产品

Policy Network 不是传统的强化学习策略网络。
它是"市场感知 + 候选生成"的混合体：

1. 分析当前市场状态（品类健康度、竞争格局、资金池状况）
2. 从基因库中挖掘高潜力模式
3. 生成 20+ 候选基因组
4. 按优先级排序，供 MCTS 深度推演

核心原则：80% 剥削（已知好的模式）+ 20% 探索（随机变异）
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from itertools import product

from core.genome import (
    Genome, SEED_GENOMES, GENE_SPACE,
    ProductType, Category, PricingModel, TargetMarket, TitlePattern,
)
from brain.knowledge import KnowledgeEngine


@dataclass
class Candidate:
    genome: Genome
    source: str          # "exploit" | "explore" | "seed_variant" | "recombine"
    priority: float      # 0-1，越高越值得推演
    rationale: str


@dataclass
class PolicyNetwork:
    """市场感知 → 候选产品生成"""

    knowledge: KnowledgeEngine = field(default_factory=KnowledgeEngine)

    def generate_candidates(self, gene_pool: dict[str, Genome],
                            fund_balance: float,
                            count: int = 20) -> list[Candidate]:
        """生成候选基因组列表"""
        candidates: list[Candidate] = []

        # 80% 剥削
        exploit_count = int(count * 0.8)
        candidates += self._exploit(gene_pool, exploit_count)

        # 20% 探索
        explore_count = count - len(candidates)
        candidates += self._explore(gene_pool, explore_count)

        # 按优先级排序
        candidates.sort(key=lambda c: c.priority, reverse=True)
        return candidates[:count]

    def _exploit(self, gene_pool: dict[str, Genome], count: int) -> list[Candidate]:
        """剥削：从已知好的模式中生成候选"""
        candidates = []

        # 按适应度排序现有基因
        ranked = sorted(
            gene_pool.values(),
            key=lambda g: (g.fitness_score, g.survival_rate),
            reverse=True,
        )

        for g in ranked[:max(count, 5)]:
            # 直接变异
            variant = g.mutate()
            candidates.append(Candidate(
                genome=variant,
                source="exploit",
                priority=g.fitness_score * 0.8 + g.survival_rate * 0.2,
                rationale=f"变异自高适应度基因 {g.genome_id[:8]} (fitness={g.fitness_score:.2f})",
            ))

            # 与另一个高适应度基因重组
            if len(ranked) > 1:
                partner = random.choice([r for r in ranked if r.genome_id != g.genome_id])
                child = g.recombine(partner)
                candidates.append(Candidate(
                    genome=child,
                    source="exploit",
                    priority=(g.fitness_score + partner.fitness_score) / 2,
                    rationale=f"重组 {g.genome_id[:6]}+{partner.genome_id[:6]}",
                ))

        return candidates[:count]

    def _explore(self, gene_pool: dict[str, Genome], count: int) -> list[Candidate]:
        """探索：尝试新的基因组合"""
        candidates = []

        strategies = [
            self._random_new_genome,
            self._extreme_price_test,
            self._new_category_test,
            self._seed_variant,
        ]

        for _ in range(count):
            strategy = random.choice(strategies)
            genome = strategy(gene_pool)
            candidates.append(Candidate(
                genome=genome,
                source="explore",
                priority=0.3,  # 探索候选优先级较低
                rationale=f"探索策略: {strategy.__name__}",
            ))

        return candidates

    def _random_new_genome(self, _=None) -> Genome:
        """完全随机的新基因组"""
        g = Genome(
            product_type=random.choice(GENE_SPACE["product_type"]),
            category=random.choice(GENE_SPACE["category"]),
            pricing_model=random.choice(GENE_SPACE["pricing_model"]),
            target_market=random.choice(GENE_SPACE["target_market"]),
            title_pattern=random.choice(GENE_SPACE["title_pattern"]),
            price_point=random.choice(GENE_SPACE["price_point"]),
            description_style=random.choice(GENE_SPACE["description_style"]),
            screenshot_count=random.choice(GENE_SPACE["screenshot_count"]),
            code_complexity=random.choice(GENE_SPACE["code_complexity"]),
        )
        return g

    def _extreme_price_test(self, _=None) -> Genome:
        """测试极端价格点"""
        base = random.choice(SEED_GENOMES).mutate()
        # 测试高价
        base.price_point = random.choice([1.99, 19.99])
        if base.price_point > 10:
            base.pricing_model = PricingModel.SUBSCRIPTION
        return base

    def _new_category_test(self, _=None) -> Genome:
        """尝试新品类"""
        base = random.choice(SEED_GENOMES).mutate()
        # 选择目前使用较少的品类
        used_cats = {Category.AI_CHAT, Category.DEV_TOOLS}
        unused = [c for c in Category if c not in used_cats]
        if unused:
            base.category = random.choice(unused)
        return base

    def _seed_variant(self, _=None) -> Genome:
        """种子基因的变体"""
        return random.choice(SEED_GENOMES).mutate()

    def select_for_mcts(self, candidates: list[Candidate], n: int = 5) -> list[Candidate]:
        """为 MCTS 选出 Top N 候选（探索+剥削平衡）"""
        if len(candidates) <= n:
            return candidates

        # 前 N-1 个最高优先级 + 1 个随机探索
        ranked = sorted(candidates, key=lambda c: c.priority, reverse=True)
        selected = ranked[:n - 1]
        # 从剩余中随机选一个
        rest = [c for c in ranked if c not in selected]
        if rest:
            selected.append(random.choice(rest))

        return selected
