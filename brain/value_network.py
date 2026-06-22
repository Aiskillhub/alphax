"""AlphaX Value Network — 基因组 → 预期收入预测

基于投放历史数据，用 DeepSeek API 做 LLM-as-Judge 预测：
给定一个基因组 + 市场上下文，预测 30 天收入范围、存活概率。

与纯统计回归不同，LLM 可以利用语义理解：
- "这个品类最近竞争加剧" → 下调预测
- "低价策略在这个市场历史表现好" → 上调预测

训练数据来自 MemorySystem 的投放记录。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.genome import Genome
from core.api_utils import call_deepseek, extract_json
from config import config


@dataclass
class ValuePrediction:
    genome_id: str
    predicted_monthly_revenue: float
    predicted_survival_prob: float
    confidence: float  # 预测置信度 0-1
    reasoning: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ValueNetwork:
    """价值网络——预测一个基因组的商业价值"""

    predictions: list[ValuePrediction] = field(default_factory=list)
    accuracy_log: list[dict] = field(default_factory=list)

    def predict(self, genome: Genome, training_data: list[dict],
                market_context: dict | None = None) -> ValuePrediction:
        """预测基因组的预期收益"""
        if not training_data or not config.deepseek_api_key:
            return self._heuristic_predict(genome, training_data)

        return self._llm_predict(genome, training_data, market_context)

    def _llm_predict(self, genome: Genome, training_data: list[dict],
                     market_context: dict | None = None) -> ValuePrediction:
        """用 DeepSeek API 做结构化预测"""
        # 取最近的训练样本（最多 20 条）
        samples = training_data[-20:]
        samples_text = "\n".join(
            f"- genome={s.get('genome_id','?')[:8]}, days={s.get('days_alive',0)}, "
            f"revenue=${s.get('total_earned',0):.2f}, survived={s.get('survived',False)}"
            for s in samples
        )

        market_text = ""
        if market_context:
            market_text = (
                f"品类: {market_context.get('category','unknown')}, "
                f"存活率: {market_context.get('survival_rate',0.5):.0%}, "
                f"竞争: {market_context.get('competition','medium')}, "
                f"平均净利: ${market_context.get('avg_net_profit',0):.0f}"
            )

        prompt = f"""你是一个市场预测专家，分析一个数字产品的预期表现。

待评估产品:
- 类型: {genome.product_type.value}
- 品类: {genome.category.value}
- 定价: ${genome.price_point:.2f} ({genome.pricing_model.value})
- 目标市场: {genome.target_market.value}
- 标题风格: {genome.title_pattern.value}
- 代码复杂度: {genome.code_complexity}

市场环境: {market_text}

历史投放数据（20条样本）:
{samples}

请预测这个产品在 30 天内的表现。返回 JSON:
{{
  "monthly_revenue": 数字（美元，30天预期总收入）,
  "survival_prob": 数字（0-1，存活30天以上的概率）,
  "confidence": 数字（0-1，你对这个预测的信心）,
  "reasoning": "简短推理（1-2句话，英文）"
}}

考虑因素:
- 同类产品的历史表现
- 定价是否合理
- 品类是否饱和
- 代码复杂度对维护成本的影响

只返回 JSON，不要其他内容。"""

        try:
            content = call_deepseek(
                prompt, config.deepseek_api_key, config.deepseek_base_url,
                temperature=0.2, max_tokens=300,
            )
            content = extract_json(content)
            parsed = json.loads(content)
            prediction = ValuePrediction(
                genome_id=genome.genome_id,
                predicted_monthly_revenue=float(parsed.get("monthly_revenue", 50)),
                predicted_survival_prob=float(parsed.get("survival_prob", 0.5)),
                confidence=float(parsed.get("confidence", 0.5)),
                reasoning=parsed.get("reasoning", ""),
            )
            self.predictions.append(prediction)
            return prediction

        except Exception:
            return self._heuristic_predict(genome, training_data)

    def _heuristic_predict(self, genome: Genome, training_data: list[dict]) -> ValuePrediction:
        """启发式预测（无 API 时的统计方法）"""
        if not training_data:
            return ValuePrediction(
                genome_id=genome.genome_id,
                predicted_monthly_revenue=genome.price_point * 10,
                predicted_survival_prob=0.5,
                confidence=0.1,
                reasoning="无历史数据，基于价格估算",
            )

        # 统计同类基因的平均表现
        survived = [s for s in training_data if s.get("survived")]
        survival_rate = len(survived) / len(training_data) if training_data else 0.5

        avg_revenue = (
            sum(s.get("total_earned", 0) for s in survived) / len(survived)
            if survived else 0
        )

        # 价格因子：高于平均价格 → 收入可能更高但转化率更低
        avg_price = 4.99
        price_factor = 1.0 if genome.price_point <= avg_price else 0.7

        predicted = avg_revenue * price_factor * survival_rate

        return ValuePrediction(
            genome_id=genome.genome_id,
            predicted_monthly_revenue=round(max(predicted, 1), 2),
            predicted_survival_prob=round(survival_rate, 2),
            confidence=min(0.5, len(training_data) / 50),
            reasoning=f"基于 {len(training_data)} 条历史数据统计，同类存活率 {survival_rate:.0%}",
        )

    def evaluate(self, predicted: ValuePrediction, actual_revenue: float,
                 actual_survived: bool) -> dict:
        """评估预测准确性，用于持续改进"""
        revenue_error = abs(predicted.predicted_monthly_revenue - actual_revenue)
        revenue_error_pct = revenue_error / max(actual_revenue, 1)

        survival_correct = (
            (predicted.predicted_survival_prob > 0.5 and actual_survived)
            or (predicted.predicted_survival_prob <= 0.5 and not actual_survived)
        )

        evaluation = {
            "genome_id": predicted.genome_id,
            "predicted_revenue": predicted.predicted_monthly_revenue,
            "actual_revenue": actual_revenue,
            "revenue_error_pct": round(revenue_error_pct, 2),
            "survival_correct": survival_correct,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.accuracy_log.append(evaluation)
        return evaluation

    @property
    def mean_revenue_error(self) -> float:
        """平均收入预测误差百分比"""
        if not self.accuracy_log:
            return float("inf")
        return sum(e["revenue_error_pct"] for e in self.accuracy_log) / len(self.accuracy_log)
