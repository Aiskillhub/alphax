"""基因组：数字生物的 DNA

基因不是代码——基因是"可继承的成功模式"。
每个基因是一个可变异、可表达、可评估的决策参数集合。

DynamicGenome: LLM 可提议新基因位点，基因空间随进化扩展。
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from enum import Enum


class ProductType(str, Enum):
    CHROME_EXTENSION = "chrome_extension"
    NOTION_TEMPLATE = "notion_template"
    VSCODE_EXTENSION = "vscode_extension"
    PROMPT_LIBRARY = "prompt_library"
    CANVA_TEMPLATE = "canva_template"
    SAAS_BOILERPLATE = "saas_boilerplate"
    WEB_TOOL = "web_tool"
    API_SERVICE = "api_service"
    MICRO_COURSE = "micro_course"


class Category(str, Enum):
    AI_CHAT = "ai_chat"
    PRODUCTIVITY = "productivity"
    DEV_TOOLS = "dev_tools"
    DATA = "data"
    CONTENT = "content"
    SEO = "seo"
    AUTOMATION = "automation"


class PricingModel(str, Enum):
    ONE_TIME = "one_time"
    SUBSCRIPTION = "subscription"
    FREEMIUM = "freemium"


class TargetMarket(str, Enum):
    ENGLISH = "english"
    CHINESE = "chinese"
    DEVELOPER = "developer"
    CONSUMER = "consumer"


class TitlePattern(str, Enum):
    ONE_CLICK = "One-Click {function} for {platform}"
    SMART = "Smart {function} — {benefit}"
    ULTIMATE = "The Ultimate {function} Tool"
    SIMPLE = "Simple {function}"
    PRO = "{function} Pro"


# LLM 后端的可选值
LLM_BACKENDS = ["deepseek", "claude", "gpt", "gemini"]

# 设计风格
DESIGN_STYLES = ["minimal", "rich", "enterprise", "playful", "brutalist"]

# Prompt 策略
PROMPT_STRATEGIES = ["default", "detailed_spec", "competitive_analysis", "user_story_driven"]


# 每个基因位点的可能值 —— 可动态扩展
GENE_SPACE: dict[str, list] = {
    "product_type": list(ProductType),
    "category": list(Category),
    "pricing_model": list(PricingModel),
    "target_market": list(TargetMarket),
    "title_pattern": list(TitlePattern),
    "price_point": [1.99, 2.99, 3.99, 4.99, 5.99, 7.99, 9.99, 14.99, 19.99],
    "description_style": ["benefit_first", "feature_list", "story", "comparison"],
    "screenshot_count": [2, 3, 4, 5],
    "code_complexity": ["minimal", "standard", "rich"],
    "llm_backend": LLM_BACKENDS,
    "design_style": DESIGN_STYLES,
    "prompt_strategy": PROMPT_STRATEGIES,
}


def add_gene_locus(name: str, values: list, value_type: str = "str") -> bool:
    """动态添加新基因位点。由 Mutator 调用。

    返回 True 如果成功添加，False 如果位点已存在。
    """
    if name in GENE_SPACE:
        return False
    if name in {"genome_id", "generation", "parent_id", "mutations",
                 "created_at", "fitness_score", "times_used", "times_succeeded"}:
        return False  # 保留字段名
    GENE_SPACE[name] = list(values)
    return True


@dataclass
class Mutation:
    field: str
    old_value: object
    new_value: object

    def __str__(self):
        return f"{self.field}: {self.old_value} → {self.new_value}"


@dataclass
class Genome:
    # 核心位点
    product_type: ProductType = ProductType.CHROME_EXTENSION
    category: Category = Category.AI_CHAT
    pricing_model: PricingModel = PricingModel.ONE_TIME
    target_market: TargetMarket = TargetMarket.ENGLISH
    title_pattern: TitlePattern = TitlePattern.ONE_CLICK
    price_point: float = 3.99
    description_style: str = "benefit_first"
    screenshot_count: int = 4
    code_complexity: str = "standard"

    # Layer 2: 策略位点（每个 organism 锁定不同 LLM 后端和设计风格）
    llm_backend: str = "deepseek"
    design_style: str = "minimal"
    prompt_strategy: str = "default"
    target_audience: str = "developers"

    # Layer 3: 可扩展位点 — LLM 可提议新字段
    extra: dict = field(default_factory=dict)

    # 遗传信息
    generation: int = 0
    parent_id: str | None = None
    mutations: list[Mutation] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    # 适应度
    fitness_score: float = 0.0
    times_used: int = 0
    times_succeeded: int = 0

    @property
    def genome_id(self) -> str:
        """基因型哈希——身份的基础"""
        raw = f"{self.product_type}{self.category}{self.pricing_model}{self.target_market}{self.title_pattern}{self.price_point}{self.llm_backend}{self.design_style}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    @property
    def survival_rate(self) -> float:
        if self.times_used == 0:
            return 0.5
        return self.times_succeeded / self.times_used

    def mutate(self, rate: float = 0.10) -> Genome:
        """产生变异后代——每个位点有概率变异"""
        child = copy.deepcopy(self)
        child.generation += 1
        child.parent_id = self.genome_id
        child.mutations = []
        child.created_at = time.time()
        child.fitness_score = 0.0
        child.times_used = 0
        child.times_succeeded = 0

        for field, options in GENE_SPACE.items():
            if random.random() >= rate:
                continue

            if field == "llm_backend":
                old = child.llm_backend
                new = random.choice([o for o in options if o != old])
                child.llm_backend = new
                child.mutations.append(Mutation(field, old, new))

            elif field == "design_style":
                old = child.design_style
                new = random.choice([o for o in options if o != old])
                child.design_style = new
                child.mutations.append(Mutation(field, old, new))

            elif field == "prompt_strategy":
                old = child.prompt_strategy
                new = random.choice([o for o in options if o != old])
                child.prompt_strategy = new
                child.mutations.append(Mutation(field, old, new))

            elif field == "target_audience":
                old = child.target_audience
                new = random.choice([o for o in options if o != old])
                child.target_audience = new
                child.mutations.append(Mutation(field, old, new))

            elif field in ("price_point", "screenshot_count"):
                old = getattr(child, field)
                factor = 1 + random.uniform(-0.25, 0.25)
                if field == "price_point":
                    new = round(old * factor, 2)
                    new = max(0.99, min(99.99, new))
                else:
                    new = int(round(old * factor))
                    new = max(1, min(10, new))
                setattr(child, field, new)
                child.mutations.append(Mutation(field, old, new))

            elif field in child.extra:
                old = child.extra[field]
                if isinstance(options[0], (int, float)):
                    factor = 1 + random.uniform(-0.25, 0.25)
                    new = type(old)(round(old * factor, 2))
                else:
                    new = random.choice([o for o in options if o != old])
                child.extra[field] = new
                child.mutations.append(Mutation(f"extra.{field}", old, new))

            elif hasattr(child, field):
                old = getattr(child, field)
                new = random.choice([o for o in options if o != old])
                setattr(child, field, new)
                child.mutations.append(Mutation(field, old, new))

        return child

    def recombine(self, other: Genome) -> Genome:
        """基因重组：两个父代杂交产生后代"""
        child = copy.deepcopy(self)
        child.generation = max(self.generation, other.generation) + 1
        child.parent_id = f"{self.genome_id}+{other.genome_id}"
        child.mutations = []
        child.created_at = time.time()

        for field in GENE_SPACE:
            if random.random() < 0.5:
                if field in child.extra:
                    child.extra[field] = other.extra.get(field, child.extra[field])
                elif hasattr(child, field) and hasattr(other, field):
                    setattr(child, field, getattr(other, field))

        return child

    def genetic_distance(self, other: Genome) -> float:
        """计算两个基因组的汉明距离"""
        fields = list(GENE_SPACE.keys())
        diffs = sum(
            1 for f in fields
            if (f in self.extra and self.extra.get(f) != other.extra.get(f))
            or (hasattr(self, f) and getattr(self, f) != getattr(other, f))
        )
        return diffs / max(1, len(fields))

    def express(self) -> str:
        """基因表达：生成可读的产品概念"""
        try:
            title = self.title_pattern.value.format(
                function=self._function_name(),
                platform=self._platform_name(),
                benefit=self.benefit,
            )
        except (KeyError, ValueError):
            # fallback for unknown format keys
            title = f"{self._function_name()} for {self._platform_name()}"
        return title

    def _function_name(self) -> str:
        names = {
            Category.AI_CHAT: "Chat Export",
            Category.PRODUCTIVITY: "Task Organizer",
            Category.DEV_TOOLS: "Code Formatter",
            Category.DATA: "Data Analyzer",
            Category.CONTENT: "Content Generator",
            Category.SEO: "SEO Optimizer",
            Category.AUTOMATION: "Workflow Automator",
        }
        return names.get(self.category, "Tool")

    def _platform_name(self) -> str:
        if self.target_market == TargetMarket.DEVELOPER:
            return "Developers"
        elif self.target_market == TargetMarket.CHINESE:
            return "中国用户"
        return "Professionals"

    @property
    def benefit(self) -> str:
        benefits = {
            Category.AI_CHAT: "Save Hours of Copy-Paste",
            Category.PRODUCTIVITY: "Get Organized Instantly",
            Category.DEV_TOOLS: "Write Better Code Faster",
            Category.DATA: "Understand Your Data in Seconds",
            Category.CONTENT: "Create Content 10x Faster",
            Category.SEO: "Rank Higher on Google",
            Category.AUTOMATION: "Automate Your Workflow",
        }
        return benefits.get(self.category, "Boost Your Productivity")

    def identity_relation(self, other: Genome) -> str:
        """判断与另一个基因组的关系"""
        d = self.genetic_distance(other)
        if d == 0:
            return "clone"
        elif d < 0.1:
            return "same_individual_variant"
        elif d < 0.3:
            return "direct_descendant"
        elif d < 0.5:
            return "variant"
        else:
            return "new_species"

    def to_dict(self) -> dict:
        return {
            "genome_id": self.genome_id,
            "product_type": self.product_type.value if isinstance(self.product_type, Enum) else str(self.product_type),
            "category": self.category.value if isinstance(self.category, Enum) else str(self.category),
            "pricing_model": self.pricing_model.value if isinstance(self.pricing_model, Enum) else str(self.pricing_model),
            "target_market": self.target_market.value if isinstance(self.target_market, Enum) else str(self.target_market),
            "title_pattern": self.title_pattern.value if isinstance(self.title_pattern, Enum) else str(self.title_pattern),
            "price_point": self.price_point,
            "description_style": self.description_style,
            "screenshot_count": self.screenshot_count,
            "code_complexity": self.code_complexity,
            "llm_backend": self.llm_backend,
            "design_style": self.design_style,
            "prompt_strategy": self.prompt_strategy,
            "target_audience": self.target_audience,
            "extra": self.extra,
            "generation": self.generation,
            "parent_id": self.parent_id,
            "fitness_score": self.fitness_score,
            "times_used": self.times_used,
            "times_succeeded": self.times_succeeded,
            "survival_rate": self.survival_rate,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Genome:
        pt = d.get("product_type", "chrome_extension")
        cat = d.get("category", "ai_chat")
        pm = d.get("pricing_model", "one_time")
        tm = d.get("target_market", "english")
        tp = d.get("title_pattern", "One-Click {function} for {platform}")

        try:
            product_type = ProductType(pt)
        except ValueError:
            product_type = ProductType.CHROME_EXTENSION
        try:
            category = Category(cat)
        except ValueError:
            category = Category.AI_CHAT
        try:
            pricing_model = PricingModel(pm)
        except ValueError:
            pricing_model = PricingModel.ONE_TIME
        try:
            target_market = TargetMarket(tm)
        except ValueError:
            target_market = TargetMarket.ENGLISH
        try:
            title_pattern = TitlePattern(tp)
        except ValueError:
            title_pattern = TitlePattern.ONE_CLICK

        g = cls(
            product_type=product_type,
            category=category,
            pricing_model=pricing_model,
            target_market=target_market,
            title_pattern=title_pattern,
            price_point=d.get("price_point", 3.99),
            description_style=d.get("description_style", "benefit_first"),
            screenshot_count=d.get("screenshot_count", 4),
            code_complexity=d.get("code_complexity", "standard"),
            llm_backend=d.get("llm_backend", "deepseek"),
            design_style=d.get("design_style", "minimal"),
            prompt_strategy=d.get("prompt_strategy", "default"),
            target_audience=d.get("target_audience", "developers"),
            extra=d.get("extra", {}),
            generation=d.get("generation", 0),
            parent_id=d.get("parent_id"),
        )
        g.fitness_score = d.get("fitness_score", 0.0)
        g.times_used = d.get("times_used", 0)
        g.times_succeeded = d.get("times_succeeded", 0)
        return g


# 初始种子基因 —— 多种 LLM 后端 + 设计风格组合
SEED_GENOMES: list[Genome] = [
    # 种子 1：AI Chat 扩展，DeepSeek 生成
    Genome(
        product_type=ProductType.CHROME_EXTENSION,
        category=Category.AI_CHAT,
        pricing_model=PricingModel.ONE_TIME,
        target_market=TargetMarket.ENGLISH,
        price_point=3.99,
        title_pattern=TitlePattern.ONE_CLICK,
        llm_backend="deepseek",
        design_style="minimal",
        prompt_strategy="default",
    ),
    # 种子 2：生产力工具，Claude 生成
    Genome(
        product_type=ProductType.CHROME_EXTENSION,
        category=Category.PRODUCTIVITY,
        pricing_model=PricingModel.ONE_TIME,
        target_market=TargetMarket.ENGLISH,
        price_point=4.99,
        title_pattern=TitlePattern.SMART,
        llm_backend="claude",
        design_style="rich",
        prompt_strategy="detailed_spec",
    ),
    # 种子 3：开发者工具，GPT 生成
    Genome(
        product_type=ProductType.CHROME_EXTENSION,
        category=Category.DEV_TOOLS,
        pricing_model=PricingModel.ONE_TIME,
        target_market=TargetMarket.DEVELOPER,
        price_point=5.99,
        title_pattern=TitlePattern.PRO,
        llm_backend="gpt",
        design_style="enterprise",
        prompt_strategy="competitive_analysis",
    ),
    # 种子 4：Notion 模板，Gemini 生成
    Genome(
        product_type=ProductType.NOTION_TEMPLATE,
        category=Category.PRODUCTIVITY,
        pricing_model=PricingModel.ONE_TIME,
        target_market=TargetMarket.ENGLISH,
        price_point=9.99,
        title_pattern=TitlePattern.SMART,
        llm_backend="gemini",
        design_style="playful",
        prompt_strategy="user_story_driven",
    ),
    # 种子 5：VS Code 扩展，DeepSeek 生成
    Genome(
        product_type=ProductType.VSCODE_EXTENSION,
        category=Category.DEV_TOOLS,
        pricing_model=PricingModel.FREEMIUM,
        target_market=TargetMarket.DEVELOPER,
        price_point=4.99,
        title_pattern=TitlePattern.PRO,
        llm_backend="deepseek",
        design_style="minimal",
        prompt_strategy="default",
    ),
    # 种子 6：AI Prompt 库，Claude 生成
    Genome(
        product_type=ProductType.PROMPT_LIBRARY,
        category=Category.AI_CHAT,
        pricing_model=PricingModel.ONE_TIME,
        target_market=TargetMarket.ENGLISH,
        price_point=7.99,
        title_pattern=TitlePattern.ULTIMATE,
        llm_backend="claude",
        design_style="rich",
        prompt_strategy="detailed_spec",
    ),
    # 种子 7：Web 工具，GPT 生成
    Genome(
        product_type=ProductType.WEB_TOOL,
        category=Category.AUTOMATION,
        pricing_model=PricingModel.ONE_TIME,
        target_market=TargetMarket.DEVELOPER,
        price_point=5.99,
        title_pattern=TitlePattern.SIMPLE,
        llm_backend="gpt",
        design_style="enterprise",
        prompt_strategy="competitive_analysis",
    ),
    # 种子 8：SaaS Boilerplate，Gemini 生成
    Genome(
        product_type=ProductType.SAAS_BOILERPLATE,
        category=Category.DEV_TOOLS,
        pricing_model=PricingModel.ONE_TIME,
        target_market=TargetMarket.DEVELOPER,
        price_point=29.99,
        title_pattern=TitlePattern.PRO,
        llm_backend="gemini",
        design_style="brutalist",
        prompt_strategy="user_story_driven",
    ),
    # 种子 9：SEO 工具，Claude 生成
    Genome(
        product_type=ProductType.WEB_TOOL,
        category=Category.SEO,
        pricing_model=PricingModel.FREEMIUM,
        target_market=TargetMarket.CONSUMER,
        price_point=14.99,
        title_pattern=TitlePattern.ULTIMATE,
        llm_backend="claude",
        design_style="minimal",
        prompt_strategy="detailed_spec",
    ),
    # 种子 10：数据工具，GPT 生成
    Genome(
        product_type=ProductType.API_SERVICE,
        category=Category.DATA,
        pricing_model=PricingModel.SUBSCRIPTION,
        target_market=TargetMarket.DEVELOPER,
        price_point=19.99,
        title_pattern=TitlePattern.PRO,
        llm_backend="gpt",
        design_style="enterprise",
        prompt_strategy="competitive_analysis",
    ),
    # 种子 11：中文市场，DeepSeek 生成
    Genome(
        product_type=ProductType.WEB_TOOL,
        category=Category.AI_CHAT,
        pricing_model=PricingModel.SUBSCRIPTION,
        target_market=TargetMarket.CHINESE,
        price_point=2.99,
        title_pattern=TitlePattern.ONE_CLICK,
        llm_backend="deepseek",
        design_style="minimal",
        prompt_strategy="default",
        target_audience="general",
    ),
    # 种子 12：内容工具，Claude 生成
    Genome(
        product_type=ProductType.WEB_TOOL,
        category=Category.CONTENT,
        pricing_model=PricingModel.ONE_TIME,
        target_market=TargetMarket.ENGLISH,
        price_point=7.99,
        title_pattern=TitlePattern.SMART,
        llm_backend="claude",
        design_style="playful",
        prompt_strategy="user_story_driven",
        target_audience="designers",
    ),
]
