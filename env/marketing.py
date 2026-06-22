"""营销自动化引擎

好产品不等于能卖出去的产品。分发才是瓶颈。

三个模块：
1. ScreenshotGenerator — 自动生成产品截图/预览
2. SEOOptimizer — 基于基因生成SEO优化的产品描述
3. CopyWriter — 社交媒体推广文案自动生成
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class MarketingAssets:
    """一套完整的营销资产"""
    product_name: str
    tagline: str                # 一句话卖点
    description_seo: str        # SEO 优化长描述
    bullet_points: list[str]    # 核心卖点列表
    social_copy: dict[str, str] # {platform: copy} — Twitter, Reddit, PH
    keywords: list[str]         # SEO 关键词
    suggested_title: str        # 最佳标题
    pricing_copy: str           # 定价说服文案
    target_audience_insight: str  # 目标用户洞察
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SEOScore:
    """SEO 质量评分"""
    keyword_density: float
    title_score: float
    description_score: float
    overall: float
    suggestions: list[str]


class MarketingEngine:
    """自动生成全套营销资产"""

    def __init__(self):
        self._assets_path = config.data_dir / "marketing_assets.jsonl"
        self._history: list[MarketingAssets] = []

    def generate_assets(self, organism, build) -> MarketingAssets | None:
        """为一个产品生成全套营销资产"""
        genome = organism.genome
        if not genome:
            return None

        # 用 LLM 生成营销内容
        if config.deepseek_api_key:
            assets = self._llm_generate(genome, build)
        else:
            assets = self._template_generate(genome)

        if assets:
            self._history.append(assets)
            self._save(assets)
        return assets

    def _llm_generate(self, genome, build) -> MarketingAssets | None:
        """用 LLM 生成高质量营销内容"""
        cat = str(getattr(genome, 'category', 'dev_tools'))
        ptype = str(getattr(genome, 'product_type', 'web_tool'))
        audience = str(getattr(genome, 'target_audience', 'developers'))
        price = getattr(genome, 'price_point', 4.99)
        design = str(getattr(genome, 'design_style', 'minimal'))

        # 从 build 中提取一些代码特征作为产品描述素材
        code_sample = ""
        for fname, content in list(build.files.items())[:2]:
            content_s = content if isinstance(content, str) else str(content)
            code_sample += f"// {fname}\n{content_s[:500]}\n\n"

        prompt = f"""You are a growth marketer for SaaS products.

## Product
- Type: {ptype}
- Category: {cat}
- Target: {audience}
- Price: ${price}
- Design: {design}

## Code Sample
{code_sample[:800]}

## Task
Generate a complete marketing package. Return JSON:

{{
  "tagline": "one compelling sentence (max 15 words)",
  "description_seo": "SEO-optimized 200-word product description with keywords",
  "bullet_points": ["benefit 1", "benefit 2", "benefit 3", "benefit 4"],
  "social_copy": {{
    "twitter": "tweet under 280 chars with hook",
    "reddit": "reddit post title that gets upvotes",
    "producthunt": "producthunt tagline"
  }},
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "suggested_title": "best product title for SEO",
  "pricing_copy": "why ${price} is a no-brainer (2 sentences)",
  "target_audience_insight": "one insight about who needs this"
}}

Output ONLY valid JSON. No markdown, no explanation."""

        try:
            body = json.dumps({
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "You are an expert SaaS marketer. Output only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.8,
                "max_tokens": 1500,
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
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    result = json.loads(content[start:end])
                else:
                    return None

            name = genome.express() if hasattr(genome, 'express') else f"{ptype} for {audience}"

            return MarketingAssets(
                product_name=str(name),
                tagline=result.get("tagline", ""),
                description_seo=result.get("description_seo", ""),
                bullet_points=result.get("bullet_points", []),
                social_copy=result.get("social_copy", {}),
                keywords=result.get("keywords", []),
                suggested_title=result.get("suggested_title", str(name)),
                pricing_copy=result.get("pricing_copy", ""),
                target_audience_insight=result.get("target_audience_insight", ""),
            )
        except Exception:
            return None

    def _template_generate(self, genome) -> MarketingAssets:
        """无 LLM 时的模板化生成"""
        cat = str(getattr(genome, 'category', 'dev_tools'))
        ptype = str(getattr(genome, 'product_type', 'web_tool'))
        audience = str(getattr(genome, 'target_audience', 'developers'))
        price = getattr(genome, 'price_point', 4.99)
        name = genome.express() if hasattr(genome, 'express') else f"{ptype} for {audience}"

        return MarketingAssets(
            product_name=str(name),
            tagline=f"The smartest {cat} tool for {audience}",
            description_seo=f"A powerful {ptype} designed for {audience}. "
                           f"Built to solve real {cat} problems with elegant {audience}-first design. "
                           f"Get started in minutes, not hours.",
            bullet_points=[
                f"One-click {cat} solution",
                f"Designed for {audience}",
                "No learning curve",
                "Works everywhere",
            ],
            social_copy={
                "twitter": f"Just launched: {name} — the {cat} tool {audience} have been waiting for. ${price}, one-time. 🚀",
                "reddit": f"I built a {ptype} that solves the most annoying {cat} problem. ${price}, no subscription.",
                "producthunt": f"{name} — {cat} made simple for {audience}",
            },
            keywords=[cat, ptype, f"{cat} tool", f"best {cat} tool", audience],
            suggested_title=str(name),
            pricing_copy=f"At just ${price}, this pays for itself in the first use. No subscription, no hidden fees.",
            target_audience_insight=f"{audience} need better {cat} tools that just work.",
        )

    def evaluate_seo(self, assets: MarketingAssets, product_type: str, category: str) -> SEOScore:
        """评估 SEO 质量"""
        desc = assets.description_seo.lower()
        title = assets.suggested_title.lower()

        # 关键词密度
        kw_matches = sum(1 for kw in assets.keywords if kw.lower() in desc)
        keyword_density = kw_matches / max(1, len(assets.keywords))

        # 标题质量
        title_score = min(1.0, len(assets.suggested_title) / 60)

        # 描述质量
        desc_score = min(1.0, len(assets.description_seo) / 500)

        suggestions = []
        if keyword_density < 0.5:
            suggestions.append("Use more target keywords in description")
        if len(assets.suggested_title) < 30:
            suggestions.append("Title too short — aim for 50-60 chars")
        if len(assets.description_seo) < 300:
            suggestions.append("Description too short — aim for 500+ chars")

        return SEOScore(
            keyword_density=round(keyword_density, 2),
            title_score=round(title_score, 2),
            description_score=round(desc_score, 2),
            overall=round((keyword_density + title_score + desc_score) / 3, 2),
            suggestions=suggestions,
        )

    def get_best_assets(self, category: str = "", limit: int = 5) -> list[MarketingAssets]:
        """获取历史最佳营销资产"""
        return self._history[-limit:]

    @property
    def summary(self) -> dict:
        return {
            "assets_generated": len(self._history),
            "latest_tagline": self._history[-1].tagline if self._history else "",
            "avg_keywords": round(
                sum(len(a.keywords) for a in self._history) / max(1, len(self._history)), 1
            ),
        }

    def _save(self, assets: MarketingAssets):
        try:
            entry = {
                "product_name": assets.product_name,
                "tagline": assets.tagline,
                "description_seo": assets.description_seo,
                "bullet_points": assets.bullet_points,
                "social_copy": assets.social_copy,
                "keywords": assets.keywords,
                "suggested_title": assets.suggested_title,
                "pricing_copy": assets.pricing_copy,
                "target_audience_insight": assets.target_audience_insight,
                "generated_at": assets.generated_at,
            }
            with open(self._assets_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass
