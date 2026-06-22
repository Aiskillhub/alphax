"""Prompt 自我进化器

Prompt 本身也是一种基因。把它从写死的模板变成可变异、可遗传、可优化的文本。

成功 organism 的 prompt 会被保留和变异，失败的会被淘汰。
LLM 自己改进自己的生成 prompt。
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class PromptGene:
    """一个 prompt 的完整进化记录"""
    prompt_id: str
    prompt_text: str
    product_type: str
    category: str
    generation: int = 0
    parent_prompt_id: str = ""
    fitness_score: float = 0.0
    times_used: int = 0
    avg_build_quality: float = 0.0   # Critic 评分的均值
    created_at: str = ""
    best_build_id: str = ""

    def __post_init__(self):
        if not self.prompt_id:
            self.prompt_id = hashlib.sha256(
                (self.prompt_text[:200] + str(self.generation)).encode()
            ).hexdigest()[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class PromptEvolver:
    """管理 prompt 的进化

    每个 organism 的 prompt_strategy 不再只是标签，
    而是可以存储实际 prompt 文本（或其 prompt_id 引用）。
    """

    _prompts_path: Path = config.data_dir / "prompt_pool.json"
    _history_path: Path = config.data_dir / "prompt_evolution.jsonl"
    prompt_pool: dict[str, PromptGene] = field(default_factory=dict)

    def __post_init__(self):
        self._load()
        if not self.prompt_pool:
            self._seed_prompts()

    def _seed_prompts(self):
        """初始化种子 prompt 池"""
        seeds = {
            "default": """You are an expert software engineer building a complete, production-ready product.

## Product Specification
- Type: {product_type}
- Category: {category}
- Design Style: {design_style}
- Target Audience: {target_audience}

## Requirements
- Generate COMPLETE, WORKING code. Every file must be fully implemented.
- Make it look professional and polished.
- Include a README.md.
- Output ONLY valid JSON: {{"filename": "content", ...}}""",

            "detailed_spec": """You are a senior product engineer. Build a polished, market-ready product.

## Product Brief
- Type: {product_type}
- Category: {category}
- Design: {design_style}
- Users: {target_audience}
- Price: ${price_point}

## Technical Requirements
1. All code must be production-ready — no placeholders, no TODOs
2. Error handling for all edge cases
3. Responsive design (mobile-first)
4. Accessibility: semantic HTML, ARIA labels
5. Performance: no render-blocking JS

## Deliverables
Return JSON with filename keys and complete file contents.
Include: index.html, README.md, and any required assets.""",

            "competitive_analysis": """You are building a commercial product that competes in the {category} market.

Study what top products in {category} do wrong:
- Most are too complex → make yours dead simple
- Most are ugly → make yours beautiful ({design_style} style)
- Most are slow → make yours instant

## Spec
- Type: {product_type}
- Target: {target_audience} willing to pay ${price_point}
- Design: {design_style}

## Output
Complete, working code as JSON: {{"filename": "content"}}.
Ship quality that justifies ${price_point}.""",

            "user_story_driven": """As a user, I want a {product_type} that helps me with {category}.

Build a product that solves real user problems:
1. What's the user's main pain point in {category}?
2. What's the simplest solution?
3. How can we delight them with {design_style} design?

## Target
{target_audience} users, ${price_point} price point.

## Requirements
- Clean, fast, intuitive
- Works on mobile and desktop
- Professional {design_style} aesthetic

Output as JSON with filenames as keys.""",
        }

        for name, text in seeds.items():
            self.prompt_pool[name] = PromptGene(
                prompt_id=name,
                prompt_text=text,
                product_type="*",
                category="*",
            )

    def evolve(self, best_prompts: list[str], worst_prompts: list[str],
               feedback: str = "") -> PromptGene | None:
        """让 LLM 基于成功/失败案例进化出更好的 prompt

        把最好的 prompt 和表现差的对比，让 LLM 合成改进版。
        """
        if not best_prompts or not config.deepseek_api_key:
            return self._crossover_evolve(best_prompts)

        evolution_prompt = f"""You are evolving a code-generation prompt template.

## Best Performing Prompts
{chr(10).join(f'--- PROMPT {i+1} ---{chr(10)}{p[:800]}' for i, p in enumerate(best_prompts[:3]))}

## Worst Performing Prompts
{chr(10).join(f'--- PROMPT {i+1} ---{chr(10)}{p[:400]}' for i, p in enumerate(worst_prompts[:2]))}

## Feedback
{feedback or 'Improve prompt quality and specificity.'}

## Task
Synthesize a NEW, IMPROVED prompt template that:
1. Keeps the effective patterns from the best prompts
2. Removes patterns found in the worst prompts
3. Is more specific about code quality requirements
4. Uses these template variables: {{product_type}}, {{category}}, {{design_style}}, {{target_audience}}, {{price_point}}

Output ONLY the new prompt text. No explanation."""

        try:
            import urllib.request
            body = json.dumps({
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "You evolve prompt templates. Output only the improved prompt text."},
                    {"role": "user", "content": evolution_prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 2000,
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
                new_text = data["choices"][0]["message"]["content"].strip()

            pg = PromptGene(
                prompt_id="",
                prompt_text=new_text,
                product_type="*",
                category="*",
                generation=max((self.prompt_pool[p].generation for p in best_prompts if p in self.prompt_pool), default=0) + 1,
                parent_prompt_id="+".join(best_prompts[:2]),
            )
            self.prompt_pool[pg.prompt_id] = pg
            self._save()
            return pg

        except Exception:
            return self._crossover_evolve(best_prompts)

    def _crossover_evolve(self, best_prompts: list[str]) -> PromptGene | None:
        """无 LLM 时的启发式进化：拼接两个最好 prompt"""
        if len(best_prompts) < 2:
            return None

        p1 = self.prompt_pool.get(best_prompts[0])
        p2 = self.prompt_pool.get(best_prompts[1])
        if not p1 or not p2:
            return None

        # 简单拼接：取 p1 前半 + p2 后半
        lines1 = p1.prompt_text.split('\n')
        lines2 = p2.prompt_text.split('\n')
        mid1 = len(lines1) // 2
        mid2 = len(lines2) // 2
        new_text = '\n'.join(lines1[:mid1] + lines2[mid2:])

        pg = PromptGene(
            prompt_id="",
            prompt_text=new_text,
            product_type="*",
            category="*",
            generation=max(p1.generation, p2.generation) + 1,
            parent_prompt_id=f"{p1.prompt_id}+{p2.prompt_id}",
        )
        self.prompt_pool[pg.prompt_id] = pg
        self._save()
        return pg

    def record_result(self, prompt_id: str, build_quality: float):
        """记录使用该 prompt 的构建质量"""
        if prompt_id in self.prompt_pool:
            pg = self.prompt_pool[prompt_id]
            pg.times_used += 1
            pg.avg_build_quality = (
                pg.avg_build_quality * (pg.times_used - 1) + build_quality
            ) / pg.times_used
            self._save()

    def get_prompt(self, prompt_id: str, genome) -> str:
        """获取格式化的 prompt"""
        pg = self.prompt_pool.get(prompt_id)
        if not pg:
            pg = self.prompt_pool.get("default")
        if not pg:
            return "Build a complete, production-ready product."

        text = pg.prompt_text
        # 安全地格式化
        try:
            return text.format(
                product_type=str(getattr(genome, 'product_type', 'web_tool')),
                category=str(getattr(genome, 'category', 'dev_tools')),
                design_style=str(getattr(genome, 'design_style', 'minimal')),
                target_audience=str(getattr(genome, 'target_audience', 'developers')),
                price_point=getattr(genome, 'price_point', 4.99),
            )
        except (KeyError, ValueError) as e:
            # 如果 format 失败，返回原始 text + 手动追加
            return text + f"\n\nProduct: {getattr(genome, 'product_type', 'web_tool')} for {getattr(genome, 'target_audience', 'developers')}"

    @property
    def best_prompts(self) -> list[PromptGene]:
        return sorted(self.prompt_pool.values(),
                     key=lambda p: p.avg_build_quality * p.times_used,
                     reverse=True)[:5]

    @property
    def summary(self) -> dict:
        best = self.best_prompts[:3]
        return {
            "total_prompts": len(self.prompt_pool),
            "total_uses": sum(p.times_used for p in self.prompt_pool.values()),
            "best_prompt_ids": [p.prompt_id for p in best],
            "best_avg_quality": round(best[0].avg_build_quality, 2) if best else 0,
        }

    def _save(self):
        try:
            data = {
                pid: {
                    "prompt_id": p.prompt_id,
                    "prompt_text": p.prompt_text,
                    "product_type": p.product_type,
                    "category": p.category,
                    "generation": p.generation,
                    "parent_prompt_id": p.parent_prompt_id,
                    "fitness_score": p.fitness_score,
                    "times_used": p.times_used,
                    "avg_build_quality": p.avg_build_quality,
                    "created_at": p.created_at,
                    "best_build_id": p.best_build_id,
                }
                for pid, p in self.prompt_pool.items()
            }
            self._prompts_path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _load(self):
        if self._prompts_path.exists():
            try:
                data = json.loads(self._prompts_path.read_text())
                for pid, d in data.items():
                    self.prompt_pool[pid] = PromptGene(**d)
            except (json.JSONDecodeError, OSError):
                pass
