"""基因池 — 进化决策引擎

合并原来 5 个 brain 文件的核心逻辑：
  alpha_brain   → decide()
  policy_network → generate_candidates()
  mcts_engine    → evaluate_scenarios()
  value_network  → predict_value(), calibrate()
  knowledge      → record_outcome(), category_health()

核心职责：从基因池中选出最优基因组，孵化后根据结果反馈更新基因评分。
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.genome import Genome, SEED_GENOMES, GENE_SPACE, Category, ProductType
from core.api_utils import call_deepseek, extract_json
from config import config


@dataclass
class Candidate:
    genome: Genome
    source: str       # "exploit" | "explore"
    priority: float
    rationale: str = ""


@dataclass
class MctsResult:
    genome: Genome
    expected_monthly_revenue: float
    survival_probability: float
    best_scenario: str = "neutral"
    worst_case_revenue: float = 0.0
    reasoning: str = ""
    confidence: float = 0.3


@dataclass
class ValuePrediction:
    genome_id: str
    predicted_monthly_revenue: float
    predicted_survival_prob: float
    confidence: float
    reasoning: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class GenePool:
    """进化决策引擎。从基因池中选优，从结果中学习。"""

    # 基因库
    gene_pool: dict[str, Genome] = field(default_factory=dict)

    # 策略知识
    strategy_map: list[dict] = field(default_factory=list)
    market_insights: dict[str, dict] = field(default_factory=dict)
    meta_patterns: list[dict] = field(default_factory=list)

    # 预测准确性追踪
    predictions: list[ValuePrediction] = field(default_factory=list)
    accuracy_log: list[dict] = field(default_factory=list)
    decision_count: int = 0

    _path: Path = config.data_dir / "genepool.json"

    def __post_init__(self):
        # 优先加载持久化的基因池
        if not self.gene_pool:
            loaded = self._load_gene_pool()
            if loaded:
                self._load_knowledge()
                return
            # 无持久化数据时用种子基因
            for g in SEED_GENOMES:
                self.gene_pool[g.genome_id] = g
        # 加载历史知识
        self._load_knowledge()

    # ═══════════════════════════════════════════
    # 决策：选基因组
    # ═══════════════════════════════════════════

    def select_genome(self, fund_balance: float, force_explore: bool = False,
                      market_context: dict | None = None) -> Genome:
        """核心决策：给定资金和市场状态，选出下一个该孵化的基因组"""
        self.decision_count += 1

        # 20% 探索预算
        if force_explore or (random.random() < config.exploration_budget):
            return self._random_genome()

        # 有 API 走完整管道
        if config.deepseek_api_key:
            return self._full_pipeline(fund_balance, market_context)

        # 无 API：统计或启发式
        if len(self.strategy_map) >= 10:
            return self._full_pipeline(fund_balance, market_context)

        return self._best_existing().mutate()

    def _full_pipeline(self, fund_balance: float, market_context: dict | None) -> Genome:
        """Policy → MCTS → Value 三阶段管道"""
        candidates = self._generate_candidates(count=20)
        top5 = self._select_top(candidates, n=5)
        results = self._evaluate_scenarios(top5)
        best = self._best_result(results)
        return best.genome if best else self._best_existing().mutate()

    # ═══════════════════════════════════════════
    # Stage 1: Policy — 候选生成
    # ═══════════════════════════════════════════

    def _generate_candidates(self, count: int = 20) -> list[Candidate]:
        """80% 剥削 + 20% 探索"""
        ranked = sorted(
            self.gene_pool.values(),
            key=lambda g: (g.fitness_score, g.survival_rate), reverse=True
        )
        candidates = []

        # 剥削：变异 + 重组高适应度基因
        for g in ranked[:max(count, 5)]:
            variant = g.mutate()
            candidates.append(Candidate(
                genome=variant, source="exploit",
                priority=g.fitness_score * 0.8 + g.survival_rate * 0.2,
                rationale=f"变异自 {g.genome_id[:8]} (fitness={g.fitness_score:.2f})",
            ))
            if len(ranked) > 1:
                partner = random.choice([r for r in ranked if r.genome_id != g.genome_id])
                child = g.recombine(partner)
                candidates.append(Candidate(
                    genome=child, source="exploit",
                    priority=(g.fitness_score + partner.fitness_score) / 2,
                    rationale=f"重组 {g.genome_id[:6]}+{partner.genome_id[:6]}",
                ))

        # 探索：随机新基因
        explore_count = max(0, count - len(candidates))
        for _ in range(explore_count):
            genome = self._random_genome()
            candidates.append(Candidate(genome=genome, source="explore", priority=0.3))

        candidates.sort(key=lambda c: c.priority, reverse=True)
        return candidates[:count]

    def _random_genome(self) -> Genome:
        return Genome(
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

    def _select_top(self, candidates: list[Candidate], n: int = 5) -> list[Candidate]:
        if len(candidates) <= n:
            return candidates
        ranked = sorted(candidates, key=lambda c: c.priority, reverse=True)
        selected = ranked[:n - 1]
        rest = [c for c in ranked if c not in selected]
        if rest:
            selected.append(random.choice(rest))
        return selected

    # ═══════════════════════════════════════════
    # Stage 2: MCTS — 情景推演
    # ═══════════════════════════════════════════

    def _evaluate_scenarios(self, candidates: list[Candidate]) -> list[MctsResult]:
        results = []
        for c in candidates:
            if config.deepseek_api_key:
                results.append(self._llm_evaluate(c.genome))
            else:
                results.append(self._heuristic_evaluate(c.genome))
        results.sort(key=lambda r: r.expected_monthly_revenue * r.survival_probability, reverse=True)
        return results

    def _llm_evaluate(self, genome: Genome) -> MctsResult:
        survival_rate = self._category_survival_rate(genome.category.value)
        prompt = f"""你是市场策略顾问。推演这个产品的三种市场情景。

产品: {genome.express()}
品类: {genome.category.value}  |  定价: ${genome.price_point:.2f} ({genome.pricing_model.value})
目标: {genome.target_market.value}  |  复杂度: {genome.code_complexity}
品类历史存活率: {survival_rate:.0%}

返回 JSON:
{{
  "optimistic": {{"revenue": 数字, "probability": 0-1, "condition": "条件"}},
  "neutral": {{"revenue": 数字, "probability": 0-1, "condition": "条件"}},
  "pessimistic": {{"revenue": 数字, "probability": 0-1, "condition": "条件"}},
  "overall_assessment": "综合评估（1-2句英文）",
  "risk_factors": ["风险"],
  "moat_sources": ["护城河"]
}}
只返回 JSON。"""
        try:
            content = call_deepseek(prompt, config.deepseek_api_key, config.deepseek_base_url, temperature=0.3, max_tokens=500)
            parsed = json.loads(extract_json(content))
            opt = parsed.get("optimistic", {})
            neu = parsed.get("neutral", {})
            pes = parsed.get("pessimistic", {})
            opt_r, opt_p = opt.get("revenue", 100), opt.get("probability", 0.25)
            neu_r, neu_p = neu.get("revenue", 50), neu.get("probability", 0.50)
            pes_r, pes_p = pes.get("revenue", 10), pes.get("probability", 0.25)
            total_p = opt_p + neu_p + pes_p
            if total_p > 0:
                opt_p, neu_p, pes_p = opt_p / total_p, neu_p / total_p, pes_p / total_p
            expected = opt_r * opt_p + neu_r * neu_p + pes_r * pes_p
            return MctsResult(
                genome=genome, expected_monthly_revenue=round(expected, 2),
                survival_probability=round(opt_p + neu_p, 2),
                best_scenario="optimistic", worst_case_revenue=round(pes_r, 2),
                reasoning=parsed.get("overall_assessment", ""), confidence=0.6,
            )
        except Exception:
            return self._heuristic_evaluate(genome)

    def _heuristic_evaluate(self, genome: Genome) -> MctsResult:
        price_factor = max(0.3, 1.0 - (genome.price_point - 3.99) / 15)
        base = genome.price_point * 15
        opt_r, neu_r, pes_r = base * price_factor * 1.5, base * price_factor, base * price_factor * 0.3
        complexity = {"minimal": 1.0, "standard": 0.85, "rich": 0.65}
        survival = 0.7 * complexity.get(genome.code_complexity, 0.85)
        expected = opt_r * 0.25 + neu_r * 0.5 + pes_r * 0.25
        return MctsResult(
            genome=genome, expected_monthly_revenue=round(expected, 2),
            survival_probability=round(survival, 2),
            reasoning=f"启发式: ${genome.price_point} × 复杂度{genome.code_complexity}", confidence=0.3,
        )

    def _best_result(self, results: list[MctsResult]) -> MctsResult | None:
        if not results:
            return None
        return max(results, key=lambda r: r.expected_monthly_revenue * r.survival_probability)

    def _best_existing(self) -> Genome:
        if self.gene_pool:
            ranked = sorted(self.gene_pool.values(), key=lambda g: g.fitness_score, reverse=True)
            return ranked[0]
        return random.choice(SEED_GENOMES)

    # ═══════════════════════════════════════════
    # Stage 3: Value — 收入预测 (交叉验证用)
    # ═══════════════════════════════════════════

    def predict_value(self, genome: Genome, training_data: list[dict] | None = None,
                      market_context: dict | None = None) -> ValuePrediction:
        if not training_data or not config.deepseek_api_key:
            return self._heuristic_predict(genome, training_data or [])
        return self._llm_predict(genome, training_data, market_context)

    def _llm_predict(self, genome: Genome, training_data: list[dict],
                     market_context: dict | None = None) -> ValuePrediction:
        samples = "\n".join(
            f"- {s.get('genome_id','?')[:8]}: revenue=${s.get('total_earned',0):.2f}, survived={s.get('survived',False)}"
            for s in training_data[-20:]
        )
        prompt = f"""预测这个产品的 30 天表现。
产品: {genome.express()} | 品类: {genome.category.value} | 定价: ${genome.price_point:.2f}
历史样本:\n{samples}
返回 JSON: {{"monthly_revenue": 数字, "survival_prob": 0-1, "confidence": 0-1, "reasoning": "1-2句英文"}}"""
        try:
            content = call_deepseek(prompt, config.deepseek_api_key, config.deepseek_base_url, temperature=0.2, max_tokens=300)
            parsed = json.loads(extract_json(content))
            pred = ValuePrediction(
                genome_id=genome.genome_id,
                predicted_monthly_revenue=float(parsed.get("monthly_revenue", 50)),
                predicted_survival_prob=float(parsed.get("survival_prob", 0.5)),
                confidence=float(parsed.get("confidence", 0.5)),
                reasoning=parsed.get("reasoning", ""),
            )
            self.predictions.append(pred)
            return pred
        except Exception:
            return self._heuristic_predict(genome, training_data)

    def _heuristic_predict(self, genome: Genome, training_data: list[dict]) -> ValuePrediction:
        if not training_data:
            return ValuePrediction(genome_id=genome.genome_id, predicted_monthly_revenue=genome.price_point * 10,
                                   predicted_survival_prob=0.5, confidence=0.1, reasoning="无历史数据")
        survived = [s for s in training_data if s.get("survived")]
        sr = len(survived) / len(training_data) if training_data else 0.5
        avg_rev = sum(s.get("total_earned", 0) for s in survived) / len(survived) if survived else 0
        price_factor = 1.0 if genome.price_point <= 4.99 else 0.7
        return ValuePrediction(
            genome_id=genome.genome_id,
            predicted_monthly_revenue=round(max(avg_rev * price_factor * sr, 1), 2),
            predicted_survival_prob=round(sr, 2),
            confidence=min(0.5, len(training_data) / 50),
            reasoning=f"基于 {len(training_data)} 条历史数据",
        )

    # ═══════════════════════════════════════════
    # 反馈闭环：从结果中学习
    # ═══════════════════════════════════════════

    def record_outcome(self, genome: Genome, survived: bool, total_earned: float,
                       total_burned: float, days_alive: int):
        """organism 死亡时调用，更新基因评分和策略知识"""
        # 更新基因池
        gid = genome.genome_id
        if gid in self.gene_pool:
            existing = self.gene_pool[gid]
            existing.times_used += 1
            if survived:
                existing.times_succeeded += 1
            net = total_earned - total_burned
            new_fitness = 0.7 * existing.fitness_score + 0.3 * (0.5 + 0.5 * max(-1, min(1, net / max(total_burned, 1))))
            existing.fitness_score = new_fitness
        else:
            genome.times_used = 1
            if survived:
                genome.times_succeeded = 1
            self.gene_pool[gid] = genome

        # 记录策略
        self.strategy_map.append({
            "category": genome.category.value,
            "price_point": genome.price_point,
            "pricing_model": genome.pricing_model.value,
            "target_market": genome.target_market.value,
            "result": {
                "survived": survived,
                "net_profit": round(total_earned - total_burned, 2),
                "days_alive": days_alive,
                "survival_rate": genome.survival_rate,
            },
        })

        # 更新品类洞察
        cat = genome.category.value
        if cat not in self.market_insights:
            self.market_insights[cat] = {"total": 0, "survived": 0, "total_revenue": 0.0}
        self.market_insights[cat]["total"] += 1
        if survived:
            self.market_insights[cat]["survived"] += 1
        self.market_insights[cat]["total_revenue"] += total_earned

        # 积累足够数据后自动发现模式
        if len(self.strategy_map) >= 20:
            self._discover_patterns()

        self._save()

    # ═══════════════════════════════════════════
    # 知识发现
    # ═══════════════════════════════════════════

    def _category_survival_rate(self, category: str) -> float:
        info = self.market_insights.get(category, {})
        total = info.get("total", 0)
        if total == 0:
            return 0.5
        return info.get("survived", 0) / total

    def category_health(self, category: str) -> dict:
        info = self.market_insights.get(category, {})
        total = info.get("total", 0)
        if total == 0:
            return {"status": "unknown", "samples": 0}
        survived = info.get("survived", 0)
        return {
            "status": "hot" if survived / total > 0.5 else "cold",
            "samples": total,
            "survival_rate": survived / total,
            "avg_revenue": info.get("total_revenue", 0) / max(total, 1),
        }

    def _discover_patterns(self):
        low_price = [s for s in self.strategy_map if s["price_point"] <= 4.99]
        high_price = [s for s in self.strategy_map if s["price_point"] >= 9.99]
        if low_price and high_price:
            low_sr = sum(1 for s in low_price if s["result"]["survived"]) / len(low_price)
            high_sr = sum(1 for s in high_price if s["result"]["survived"]) / len(high_price)
            if low_sr > high_sr * 1.5:
                self._upsert("pricing", "低价策略存活率显著高于高价", f"{low_sr:.0%} vs {high_sr:.0%}", 0.85)

    def _upsert(self, tag: str, title: str, detail: str, confidence: float):
        for p in self.meta_patterns:
            if p["title"] == title:
                p["confidence"] = confidence
                return
        self.meta_patterns.append({"tag": tag, "title": title, "detail": detail, "confidence": confidence})

    @property
    def hit_rate(self) -> float:
        if not self.accuracy_log:
            return 0.5
        correct = sum(1 for e in self.accuracy_log if e.get("survival_correct"))
        return correct / len(self.accuracy_log)

    # ═══════════════════════════════════════════
    # 持久化
    # ═══════════════════════════════════════════

    def _save(self):
        self._path.write_text(json.dumps({
            "gene_pool": {gid: g.to_dict() for gid, g in self.gene_pool.items()},
            "strategy_map": self.strategy_map[-500:],
            "market_insights": self.market_insights,
            "meta_patterns": self.meta_patterns,
            "decision_count": self.decision_count,
        }, indent=2, default=str))

    def _load_knowledge(self):
        kp = config.data_dir / "knowledge.json"
        if kp.exists():
            try:
                data = json.loads(kp.read_text())
                self.market_insights = data.get("market_insights", {})
                self.strategy_map = data.get("strategy_map", [])
                self.meta_patterns = data.get("meta_patterns", [])
            except (json.JSONDecodeError, OSError):
                pass

    def _load_gene_pool(self) -> bool:
        """从 genepool.json 加载基因池，返回是否成功"""
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                pool_data = data.get("gene_pool", {})
                for gid, gdict in pool_data.items():
                    self.gene_pool[gid] = Genome.from_dict(gdict)
                self.strategy_map = data.get("strategy_map", [])
                self.market_insights = data.get("market_insights", {})
                self.meta_patterns = data.get("meta_patterns", [])
                self.decision_count = data.get("decision_count", 0)
                return len(pool_data) > 0
            except (json.JSONDecodeError, OSError):
                pass
        return False
