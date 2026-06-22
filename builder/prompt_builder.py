"""AlphaX Builder — AI Prompt 库生成器

生成结构化的 AI Prompt 库（JSON 格式，可导入各种 AI 工具）。
Prompt 库是 2026 年增长最快的数字产品子品类。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from core.genome import Genome, Category
from config import config


PROMPT_COLLECTIONS = {
    Category.AI_CHAT: {
        "name": "Chat AI Mastery Pack",
        "prompts": [
            {
                "id": "chat_expert",
                "title": "Expert Role Play",
                "prompt": "You are a world-class {domain} expert with 20+ years of experience. I need your advice on: {question}. Please provide a detailed, actionable response with concrete examples and step-by-step guidance.",
                "variables": ["domain", "question"],
                "category": "role_play",
                "use_case": "Get expert-level responses on any topic",
            },
            {
                "id": "chain_of_thought",
                "title": "Chain of Thought Problem Solver",
                "prompt": "Let's solve this step by step:\n\nProblem: {problem}\n\nStep 1: Understand the problem\nStep 2: Identify constraints\nStep 3: Generate possible solutions\nStep 4: Evaluate each solution\nStep 5: Recommend the best approach\n\nPlease work through each step before giving your final answer.",
                "variables": ["problem"],
                "category": "reasoning",
                "use_case": "Complex problem solving and analysis",
            },
            {
                "id": "content_creator",
                "title": "Content Creator Studio",
                "prompt": "Create {content_type} about {topic}.\n\nTarget audience: {audience}\nTone: {tone}\nLength: {length}\nKey points to cover:\n{points}\n\nMake it engaging, well-structured, and actionable.",
                "variables": ["content_type", "topic", "audience", "tone", "length", "points"],
                "category": "content",
                "use_case": "Generate any type of content with full control",
            },
            {
                "id": "code_reviewer",
                "title": "Code Review Assistant",
                "prompt": "Review the following {language} code:\n\n```{language}\n{code}\n```\n\nAnalyze:\n1. Code quality and readability\n2. Performance issues\n3. Security vulnerabilities\n4. Best practices violations\n5. Suggested improvements\n\nProvide specific, actionable feedback with code examples.",
                "variables": ["language", "code"],
                "category": "development",
                "use_case": "Get professional code reviews instantly",
            },
            {
                "id": "summarizer",
                "title": "Deep Summarizer",
                "prompt": "Summarize the following text in {format} format.\n\nKey requirements:\n- Length: {word_count} words\n- Focus on: {focus}\n- Include: key findings, methodology, conclusions\n\nText:\n{text}",
                "variables": ["format", "word_count", "focus", "text"],
                "category": "summarization",
                "use_case": "Summarize articles, papers, or documents",
            },
            {
                "id": "brainstorming",
                "title": "Idea Storm Generator",
                "prompt": "I need {count} creative ideas for {topic}.\n\nContext: {context}\nConstraints: {constraints}\nTarget: {target}\n\nFor each idea, provide:\n1. Name & one-line description\n2. Why it works\n3. Potential challenges\n4. First step to execute",
                "variables": ["count", "topic", "context", "constraints", "target"],
                "category": "creative",
                "use_case": "Generate and evaluate creative ideas",
            },
            {
                "id": "data_analyst",
                "title": "Data Analysis Partner",
                "prompt": "Analyze this data and provide insights:\n\nData:\n{data}\n\nAnalysis requested:\n{analysis_type}\n\nFormat: {output_format}\n\nInclude: statistical significance, trends, outliers, recommendations.",
                "variables": ["data", "analysis_type", "output_format"],
                "category": "analysis",
                "use_case": "Quick data analysis and insights",
            },
        ],
    },
    Category.DEV_TOOLS: {
        "name": "Developer Prompt Toolkit",
        "prompts": [
            {
                "id": "debug_expert",
                "title": "Debug Expert",
                "prompt": "Debug the following error:\n\nLanguage: {language}\nError:\n```\n{error}\n```\n\nCode:\n```{language}\n{code}\n```\n\nPlease:\n1. Explain the root cause\n2. Show the fix with code\n3. Explain why the fix works\n4. Suggest how to prevent this in the future",
                "variables": ["language", "error", "code"],
                "category": "debugging",
            },
            {
                "id": "api_designer",
                "title": "API Design Consultant",
                "prompt": "Design a REST API for: {project}\n\nRequirements:\n{requirements}\n\nProvide:\n1. Endpoint list with methods\n2. Request/response schemas\n3. Authentication strategy\n4. Error handling approach\n5. Rate limiting considerations",
                "variables": ["project", "requirements"],
                "category": "architecture",
            },
            {
                "id": "test_writer",
                "title": "Test Suite Generator",
                "prompt": "Write comprehensive tests for:\n\n```{language}\n{code}\n```\n\nInclude:\n- Unit tests for each function\n- Edge cases\n- Error handling tests\n- Integration test scenarios\n\nUse {framework} testing framework.",
                "variables": ["language", "code", "framework"],
                "category": "testing",
            },
            {
                "id": "sql_optimizer",
                "title": "SQL Query Optimizer",
                "prompt": "Optimize this SQL query:\n\n```sql\n{query}\n```\n\nTable schemas:\n{schema}\n\nAnalyze:\n1. Query plan issues\n2. Missing indexes\n3. Rewrite suggestions\n4. Estimated performance improvement",
                "variables": ["query", "schema"],
                "category": "database",
            },
        ],
    },
    Category.CONTENT: {
        "name": "Content Creator's AI Companion",
        "prompts": [
            {
                "id": "seo_writer",
                "title": "SEO Content Writer",
                "prompt": "Write an SEO-optimized {content_type} about {topic}.\n\nTarget keyword: {keyword}\nSecondary keywords: {secondary_keywords}\nWord count: {word_count}\n\nStructure:\n1. Compelling H1 with keyword\n2. Introduction (hook + keyword)\n3. H2 sections with keyword variations\n4. Actionable takeaways\n5. Meta description (155 chars)",
                "variables": ["content_type", "topic", "keyword", "secondary_keywords", "word_count"],
                "category": "seo",
            },
            {
                "id": "social_media",
                "title": "Social Media Multi-Platform",
                "prompt": "Create {count} social media posts about {topic}.\n\nPlatforms: {platforms}\nTone: {tone}\nGoal: {goal}\n\nFor each platform, provide:\n1. Post text (within platform limits)\n2. Hashtag strategy\n3. Best posting time\n4. Expected engagement",
                "variables": ["count", "topic", "platforms", "tone", "goal"],
                "category": "social",
            },
        ],
    },
}

_DEFAULT_PROMPTS = {
    "name": "AI Prompt Starter Pack",
    "prompts": [
        {
            "id": "assistant",
            "title": "General Assistant",
            "prompt": "Help me with: {task}\n\nContext: {context}\n\nProvide a clear, actionable response.",
            "variables": ["task", "context"],
            "category": "general",
            "use_case": "General purpose assistance",
        },
        {
            "id": "writer",
            "title": "Writing Assistant",
            "prompt": "Write a {format} about {topic}.\n\nStyle: {style}\nLength: {length}\nAudience: {audience}",
            "variables": ["format", "topic", "style", "length", "audience"],
            "category": "writing",
            "use_case": "Content creation",
        },
    ],
}


class PromptBuilder:
    """生成 AI Prompt 库"""

    _build_dir: Path = config.data_dir / "builds"

    def build(self, genome: Genome, organism_id: str) -> Path:
        self._build_dir.mkdir(parents=True, exist_ok=True)
        work_dir = self._build_dir / f"prompt_{organism_id}"
        work_dir.mkdir(exist_ok=True)

        collection = PROMPT_COLLECTIONS.get(
            genome.category, _DEFAULT_PROMPTS)

        # Main prompt library JSON
        prompt_data = {
            "library_name": collection["name"],
            "version": "1.0.0",
            "description": f"{genome.benefit}. A curated collection of {len(collection['prompts'])} high-quality AI prompts.",
            "category": genome.category.value,
            "total_prompts": len(collection["prompts"]),
            "prompts": collection["prompts"],
        }
        (work_dir / "prompts.json").write_text(
            json.dumps(prompt_data, indent=2, ensure_ascii=False))

        # Usage guide
        (work_dir / "HOW_TO_USE.md").write_text(
            self._usage_guide(genome, collection))

        # Platform-specific format
        self._export_platform_formats(work_dir, collection)

        zip_path = self._build_dir / f"{organism_id}_prompts.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in work_dir.iterdir():
                zf.write(f, f.name)

        return zip_path

    def _export_platform_formats(self, work_dir: Path, collection: dict):
        """导出各平台的 prompt 格式"""
        # ChatGPT custom instructions format
        gpt = {"custom_instructions": []}
        for p in collection["prompts"]:
            gpt["custom_instructions"].append({
                "title": p["title"],
                "about": p.get("use_case", ""),
                "prompt": p["prompt"],
            })
        (work_dir / "chatgpt_custom_instructions.json").write_text(
            json.dumps(gpt, indent=2))

        # Simple text format (copy-paste ready)
        lines = [f"# {collection['name']}\n"]
        for p in collection["prompts"]:
            lines.append(f"## {p['title']}")
            lines.append(f"Category: {p['category']}")
            lines.append(f"Use case: {p.get('use_case', 'N/A')}")
            if p.get("variables"):
                lines.append(f"Variables: {', '.join(p['variables'])}")
            lines.append(f"\n```\n{p['prompt']}\n```\n---\n")
        (work_dir / "prompts.txt").write_text("\n".join(lines))

    def _usage_guide(self, genome: Genome, collection: dict) -> str:
        return f"""# How to Use Your {collection['name']}

## Quick Start

1. Open the `prompts.json` file
2. Find a prompt that matches your task
3. Copy the prompt template
4. Replace variables marked with `{{{{variable_name}}}}`
5. Paste into ChatGPT, Claude, DeepSeek, or any AI tool

## Included Formats

- `prompts.json` — Full library with metadata
- `prompts.txt` — Copy-paste ready text format
- `chatgpt_custom_instructions.json` — Import into ChatGPT

## Tips

- Customize prompts for your specific use case
- Combine prompts for complex workflows
- Save your best variations

---
Built by Alpha X | {genome.express()}
"""
