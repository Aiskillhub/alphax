"""AlphaX Listing — Gumroad 商品页文案生成

根据基因组参数 + 市场数据，用 DeepSeek API 生成高转化率的
商品标题、描述、卖点列表。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from core.genome import Genome, Category, TargetMarket, PricingModel
from core.api_utils import call_deepseek, extract_json
from config import config


@dataclass
class ListingCopy:
    title: str
    subtitle: str
    description: str
    bullets: list[str]
    target_audience: str
    seo_keywords: list[str]


class ListingGenerator:
    """生成 Gumroad 商品页文案"""

    def generate(self, genome: Genome, market_context: dict | None = None) -> ListingCopy:
        """根据基因组生成完整商品文案"""
        context_str = ""
        if market_context:
            context_str = (
                f"市场数据: 同类存活率 {market_context.get('survival_rate', 0.5):.0%}, "
                f"平均售价 ${market_context.get('avg_price', 3.99):.2f}, "
                f"竞争密度 {market_context.get('competition', 'medium')}"
            )

        if config.deepseek_api_key:
            return self._ai_generate(genome, context_str)
        return self._template_generate(genome)

    def _ai_generate(self, genome: Genome, context: str) -> ListingCopy:
        """用 DeepSeek API 生成文案"""
        prompt = f"""你是一个 Gumroad 商品文案专家。为一个 Chrome Extension 生成完整的商品页文案。

产品参数:
- 品类: {genome.category.value}
- 目标用户: {genome.target_market.value}
- 定价: ${genome.price_point:.2f} ({genome.pricing_model.value})
- 核心功能: {genome.benefit}

{context}

请生成以下内容，返回 JSON:
{{
  "title": "商品标题（英文，50字以内，包含核心关键词）",
  "subtitle": "副标题（一句价值主张，30字以内）",
  "description": "详细描述（150-300字，HTML格式）",
  "bullets": ["卖点1", "卖点2", "卖点3", "卖点4"],
  "target_audience": "目标用户画像（一句话）",
  "seo_keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"]
}}

要求:
- 标题要突出具体功能，不要空洞的口号
- 卖点要量化（"节省 2 小时手动导出时间" 而不是 "提高效率"）
- 描述要有场景感（用户在什么情况下需要这个工具）
- 英文输出"""

        try:
            content = call_deepseek(
                prompt, config.deepseek_api_key, config.deepseek_base_url,
                temperature=0.7, max_tokens=800,
            )
            content = extract_json(content)
            parsed = json.loads(content)
            return ListingCopy(
                title=parsed.get("title", genome.express()),
                subtitle=parsed.get("subtitle", genome.benefit),
                description=parsed.get("description", self._fallback_description(genome)),
                bullets=parsed.get("bullets", self._fallback_bullets(genome)),
                target_audience=parsed.get("target_audience", "AI tool users"),
                seo_keywords=parsed.get("seo_keywords", ["chrome extension", "ai tool", "productivity"]),
            )
        except Exception:
            return self._template_generate(genome)

    def _template_generate(self, genome: Genome) -> ListingCopy:
        """模板生成（无需 API）"""
        title = genome.express()
        benefit = genome.benefit

        audience_map = {
            "english": "English-speaking professionals who use AI tools daily",
            "chinese": "中国 AI 用户，每天与 ChatGPT/Claude 对话",
            "developer": "Developers and technical professionals",
            "consumer": "Everyday users looking to boost productivity",
        }
        audience = audience_map.get(genome.target_market.value, "AI tool users")

        keywords_base = ["chrome extension", "ai tools", "productivity"]
        if genome.category == Category.AI_CHAT:
            keywords_base += ["chat export", "conversation backup", "markdown export"]
        elif genome.category == Category.DEV_TOOLS:
            keywords_base += ["developer tools", "code analysis", "web inspector"]
        elif genome.category == Category.PRODUCTIVITY:
            keywords_base += ["task management", "workflow", "organization"]

        return ListingCopy(
            title=title,
            subtitle=benefit,
            description=self._fallback_description(genome),
            bullets=self._fallback_bullets(genome),
            target_audience=audience,
            seo_keywords=keywords_base[:5],
        )

    def _fallback_description(self, genome: Genome) -> str:
        pricing = {
            "one_time": "Pay once, use forever. No subscriptions, no hidden fees.",
            "subscription": "Monthly subscription with continuous updates and new features.",
            "freemium": "Start free, upgrade when you need more power.",
        }
        return (
            f"<p>{genome.benefit}</p>"
            f"<p>This Chrome Extension works seamlessly across all major AI platforms, "
            f"letting you export, search, and organize your conversations with a single click. "
            f"No more copy-pasting or losing important discussions.</p>"
            f"<p><strong>{pricing.get(genome.pricing_model.value, '')}</strong></p>"
        )

    def _fallback_bullets(self, genome: Genome) -> list[str]:
        return [
            "One-click operation — no setup required",
            f"{genome.benefit}",
            "Works on all major AI platforms",
            "Clean, intuitive interface",
        ]
