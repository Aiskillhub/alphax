"""AlphaX Market Intelligence — 市场情报

让 autonomous 知道什么值得做，不是瞎造。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class MarketInsight:
    """一个市场发现"""
    keyword: str              # 关键词
    pain_point: str           # 用户痛点
    target_user: str          # 谁需要
    existing_solutions: str   # 现有方案（竞品、免费替代）
    why_gap: str              # 为什么还有机会
    suggested_price: float    # 建议定价
    category: str             # 产品类型
    confidence: float = 0.5   # 0-1 确信度


class MarketBrain:
    """市场研究大脑：分析需求、找痛点、评估竞争"""

    def __init__(self):
        from config import config
        self._api_key = config.deepseek_api_key
        self._base_url = config.deepseek_base_url

    def research_opportunities(self, n: int = 5) -> list[MarketInsight]:
        """研究市场，返回真正有机会的产品方向。"""
        if not self._api_key:
            return self._fallback()

        try:
            from core.api_utils import call_deepseek
            prompt = """你是数字产品市场分析师。找出 5 个有真实市场需求的数字产品方向。

## 要求
- 不是通用工具（JSON格式化、密码生成器太泛了）
- 有具体的目标用户和痛点
- Gumroad/Payhip 等平台有人愿意付费
- 单人开发能完成
- 产品类型：chrome_extension / web_tool / prompt_library / notion_template / vscode_extension

## 对每个方向，分析：
1. 目标用户是谁
2. 他们有什么具体痛点
3. 现有解决方案（竞品）是什么
4. 为什么还有机会（竞品哪里做得不好）
5. 建议定价

## 输出 JSON 数组：
[
  {
    "keyword": "产品名",
    "pain_point": "用户痛点（一句话）",
    "target_user": "目标用户",
    "existing_solutions": "现有方案",
    "why_gap": "为什么有机可乘",
    "suggested_price": 4.99,
    "category": "web_tool",
    "confidence": 0.7
  }
]

JSON:"""

            import json as jmod
            raw = call_deepseek(
                prompt, self._api_key, self._base_url,
                temperature=0.8, max_tokens=800, timeout=45,
            )
            data = jmod.loads(raw.strip().split("```")[1].strip() if "```" in raw else raw.strip())

            insights = []
            for item in data[:n]:
                insights.append(MarketInsight(
                    keyword=item.get("keyword", ""),
                    pain_point=item.get("pain_point", ""),
                    target_user=item.get("target_user", ""),
                    existing_solutions=item.get("existing_solutions", ""),
                    why_gap=item.get("why_gap", ""),
                    suggested_price=float(item.get("suggested_price", 4.99)),
                    category=item.get("category", "web_tool"),
                    confidence=float(item.get("confidence", 0.5)),
                ))
            return insights
        except Exception:
            return self._fallback()

    def _fallback(self) -> list[MarketInsight]:
        """无 LLM 时用精选方向（不是通用工具，有真实需求）。"""
        ideas = [
            MarketInsight(
                keyword="小红书文案生成器",
                pain_point="博主每天要写多条文案，没灵感，重复劳动",
                target_user="小红书博主、电商卖家",
                existing_solutions="手动写、ChatGPT 对话",
                why_gap="通用 AI 不懂小红书风格，需要专门训练的模板",
                suggested_price=6.99, category="web_tool", confidence=0.7,
            ),
            MarketInsight(
                keyword="YouTube 视频一键总结",
                pain_point="长视频不想看，需要快速提取要点",
                target_user="学生、上班族、研究者",
                existing_solutions="YouTube 自带摘要（不准）、手动笔记",
                why_gap="现有方案不准或不方便，浏览器扩展一键出更好",
                suggested_price=3.99, category="chrome_extension", confidence=0.65,
            ),
            MarketInsight(
                keyword="独立开发者定价计算器",
                pain_point="不知道产品该定多少钱，怕定高了没人买低了亏",
                target_user="独立开发者、SaaS创业者",
                existing_solutions="Excel 模板、直觉定价",
                why_gap="没有针对数字产品的智能定价工具，都太泛",
                suggested_price=5.99, category="web_tool", confidence=0.6,
            ),
            MarketInsight(
                keyword="电商客服话术模板",
                pain_point="小卖家不懂怎么回客户，复购率低",
                target_user="淘宝/拼多多/Shopify 小卖家",
                existing_solutions="百度搜模板、自己琢磨",
                why_gap="没有针对不同场景的 AI 话术库，小卖家不会写",
                suggested_price=4.99, category="prompt_library", confidence=0.65,
            ),
            MarketInsight(
                keyword="Notion 个人财务模板",
                pain_point="记账软件太复杂，Excel 太丑",
                target_user="想理财但不想学专业软件的年轻人",
                existing_solutions="随手记、Excel、空白 Notion",
                why_gap="现有方案要么太重要么太丑，Notion 模板刚好",
                suggested_price=6.99, category="notion_template", confidence=0.55,
            ),
        ]
        return ideas
