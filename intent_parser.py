"""AlphaX Arena — 意图解析器

用户自然语言 → 结构化 ArenaTask → Genome 种子。

用法：
  parser = IntentParser()
  task, genome = parser.parse("帮我做一个YouTube视频总结的Chrome扩展")
"""

from __future__ import annotations

import copy
import json
import random
import uuid

from arena_models import ArenaTask
from config import config
from core.api_utils import call_deepseek, extract_json
from core.genome import (
    Genome, ProductType, Category, PricingModel, TargetMarket, TitlePattern, DESIGN_STYLES,
)


# ── 产品类型关键词映射（LLM 离线时的 fallback）──

TYPE_KEYWORDS: dict[str, ProductType] = {
    "chrome": ProductType.CHROME_EXTENSION,
    "扩展":   ProductType.CHROME_EXTENSION,
    "插件":   ProductType.CHROME_EXTENSION,
    "浏览器": ProductType.CHROME_EXTENSION,
    "vscode": ProductType.VSCODE_EXTENSION,
    "vs code": ProductType.VSCODE_EXTENSION,
    "网页":   ProductType.WEB_TOOL,
    "工具":   ProductType.WEB_TOOL,
    "web":   ProductType.WEB_TOOL,
    "notion": ProductType.NOTION_TEMPLATE,
    "模板":   ProductType.NOTION_TEMPLATE,
    "提示词": ProductType.PROMPT_LIBRARY,
    "prompt": ProductType.PROMPT_LIBRARY,
    "ai":     ProductType.PROMPT_LIBRARY,
}

CATEGORY_KEYWORDS: dict[str, Category] = {
    "ai": Category.AI_CHAT,
    "聊天": Category.AI_CHAT,
    "效率": Category.PRODUCTIVITY,
    "工具": Category.PRODUCTIVITY,
    "开发": Category.DEV_TOOLS,
    "代码": Category.DEV_TOOLS,
    "数据": Category.DATA,
    "分析": Category.DATA,
    "内容": Category.CONTENT,
    "写作": Category.CONTENT,
    "自动化": Category.AUTOMATION,
    "自动": Category.AUTOMATION,
}


class IntentParser:
    """自然语言 → Genome 解析器"""

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or config.freellmapi_key or config.deepseek_api_key
        self._base_url = config.freellmapi_url or config.deepseek_base_url

    def parse(
        self,
        description: str,
        product_type: str = "",
    ) -> tuple[ArenaTask, Genome]:
        """解析用户意图，返回任务描述 + 基因种子。

        Args:
            description: 用户自然语言描述
            product_type: 可选，强制指定产品类型（chrome_extension / web_tool / ...）

        Returns:
            (ArenaTask, Genome) — 任务 + 基因种子
        """
        task_id = uuid.uuid4().hex[:10]

        # 先用关键词快速猜测类型（作为 LLM fallback）
        guessed_type = product_type or self._guess_type(description)
        guessed_cat = self._guess_category(description)

        # 调 LLM 深度解析
        if self._api_key:
            extracted = self._llm_parse(description, guessed_type)
        else:
            extracted = {}

        task = ArenaTask(
            task_id=task_id,
            description=description,
            product_type=extracted.get("product_type", guessed_type),
            name=extracted.get("name", self._auto_name(description)),
            features=extracted.get("features", [description]),
            design_style=extracted.get("design_style", "minimal"),
            target_market=extracted.get("target_market", "english"),
            constraints=extracted.get("constraints", []),
        )

        genome = self._to_genome(task, guessed_cat)
        return task, genome

    def generate_seeds(
        self, description: str, product_type: str = "", n_seeds: int = 3
    ) -> list[Genome]:
        """生成多个不同方向的种子基因，让 Agent 有真正的多样性。

        每个种子代表一种设计理念：极简/功能/游戏化/专业/...
        各 Agent 从不同种子出发，而非同一个种子的微小变异。
        """
        tried_styles = set()
        seeds = []

        # 基础种子（标准解析）
        task, base_seed = self.parse(description, product_type)
        seeds.append(base_seed)
        tried_styles.add(base_seed.design_style)

        if n_seeds <= 1 or not self._api_key:
            return seeds

        # 调 LLM 生成不同设计方向
        try:
            prompt = f"""你是产品设计师。为以下需求提出 {n_seeds} 种完全不同的设计方向。

## 用户需求
{description}

## 产品类型
{product_type}

## 要求
每种方向有不同的设计理念和实现方法。输出 JSON 数组：

[
  {{"design_style": "minimal|rich|playful|enterprise|brutalist", "approach": "设计理念描述（20字以内）"}},
  ...
]

JSON:"""

            raw = call_deepseek(
                prompt, self._api_key, self._base_url,
                temperature=0.8, max_tokens=500, timeout=30,
            )
            import json
            data = json.loads(extract_json(raw))
            if isinstance(data, list):
                for item in data:
                    style = item.get("design_style", "minimal")
                    if style not in DESIGN_STYLES or style in tried_styles:
                        style = [s for s in DESIGN_STYLES if s not in tried_styles][0] if len(tried_styles) < len(DESIGN_STYLES) else style
                    tried_styles.add(style)

                    # 基于该方向创建新种子
                    variant = copy.deepcopy(base_seed)
                    variant.design_style = style
                    variant.price_point = round(4.99 + random.uniform(0, 3), 2)
                    if variant.extra:
                        variant.extra["approach"] = item.get("approach", "")
                    seeds.append(variant)

                    if len(seeds) >= n_seeds:
                        break
        except Exception:
            pass

        # 如果 LLM 没返回够，手动补几个不同风格的
        fallback_styles = ["playful", "enterprise", "brutalist", "rich"]
        for style in fallback_styles:
            if len(seeds) >= n_seeds:
                break
            if style not in tried_styles:
                variant = copy.deepcopy(base_seed)
                variant.design_style = style
                variant.price_point = round(4.99 + random.uniform(0, 3), 2)
                seeds.append(variant)
                tried_styles.add(style)

        return seeds[:n_seeds]

    # ── 猜测 ──

    def _guess_type(self, text: str) -> str:
        text_lower = text.lower()
        for kw, pt in TYPE_KEYWORDS.items():
            if kw in text_lower:
                return pt.value
        return ProductType.WEB_TOOL.value

    def _guess_category(self, text: str) -> Category:
        text_lower = text.lower()
        for kw, cat in CATEGORY_KEYWORDS.items():
            if kw in text_lower:
                return cat
        return Category.PRODUCTIVITY

    @staticmethod
    def _auto_name(text: str) -> str:
        """万一名 LLM 没返回名字，从描述截取。"""
        # 去掉常见前缀
        for prefix in ["帮我", "做一个", "我想要", "我需要", "我想"]:
            text = text.replace(prefix, "")
        return text.strip()[:20]

    # ── LLM 解析 ──

    def _llm_parse(self, description: str, product_type: str) -> dict:
        """调 LLM 提取结构化信息。"""
        prompt = f"""你是资深产品经理。分析用户需求，提取关键信息。

## 用户描述
{description}

## 产品类型
{product_type}

## 任务
提取以下字段，输出严格 JSON：

{{
  "name": "<产品名称，中文，10字以内>",
  "features": ["<功能1>", "<功能2>", "..."],
  "design_style": "minimal | rich | playful | enterprise",
  "target_market": "english | chinese | developer | consumer",
  "constraints": ["<约束1>", ...]
}}

JSON:"""

        try:
            raw = call_deepseek(
                prompt, self._api_key, self._base_url,
                temperature=0.3, max_tokens=400, timeout=30,
            )
            data = json.loads(extract_json(raw))
            # 校验字段
            if not isinstance(data.get("features"), list):
                data["features"] = [description]
            if data.get("design_style") not in DESIGN_STYLES:
                data["design_style"] = "minimal"
            return data
        except Exception:
            return {}

    # ── 转 Genome ──

    def _to_genome(self, task: ArenaTask, category: Category) -> Genome:
        """ArenaTask → Genome 种子。"""
        pt = ProductType(task.product_type) if task.product_type in {
            "chrome_extension", "web_tool", "vscode_extension",
            "notion_template", "prompt_library", "canva_template",
            "saas_boilerplate", "api_service", "micro_course",
        } else ProductType.WEB_TOOL

        tm = TargetMarket.ENGLISH
        if task.target_market == "chinese":
            tm = TargetMarket.CHINESE
        elif task.target_market == "developer":
            tm = TargetMarket.DEVELOPER

        # 功能特征序列化到 genome（用作交叉/变异时的差异来源）
        features_hash = hash("|".join(task.features)) & 0xFFFF

        return Genome(
            product_type=pt,
            category=category,
            pricing_model=PricingModel.ONE_TIME,
            target_market=tm,
            price_point=4.99 + (features_hash % 100) / 100,
            title_pattern=TitlePattern.SMART,
            design_style=task.design_style if task.design_style in DESIGN_STYLES else "minimal",
            extra={
                "custom_request": task.description,
                "features": task.features,
                "name": task.name,
            },
        )
