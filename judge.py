"""AlphaX Arena — 自动裁判

评审 Agent 生成的代码质量。不依赖真实市场数据，纯 AI 审查。

评测维度（各 0-100）：
  completeness   — 文件齐全度、结构完整
  functionality  — 功能是否匹配用户需求
  code_quality   — 代码结构、可读性、错误
  design         — UI/UX 设计质量
  overall        — 加权总分

用法：
  judge = Judge()
  score = judge.evaluate(zip_path, task, agent_name)
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from arena_models import ArenaTask, Score
from config import config
from core.api_utils import call_deepseek, extract_json


# ── 需要评审的关键文件 ──

PRODUCT_FILES = {
    "chrome_extension": ["manifest.json", "content.js", "background.js", "popup.html", "popup.js"],
    "web_tool":        ["index.html"],
    "vscode_extension": ["package.json", "extension.js"],
    "notion_template": ["template.json", "README.md"],
    "prompt_library":  ["prompts.json", "README.md"],
}

MAX_FILES_TO_SHOW = 6    # 最多发给 LLM 的文件数
MAX_FILE_BYTES = 8000    # 单文件最大尺寸


class Judge:
    """AI 代码裁判。调 LLM 多维度审查生成的代码。"""

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or config.freellmapi_key or config.deepseek_api_key
        self._base_url = config.freellmapi_url or config.deepseek_base_url

    # ── 公开接口 ──

    def evaluate(
        self,
        zip_path: Path | str,
        task: ArenaTask,
        agent_name: str = "",
    ) -> Score:
        """评审一个代码包，返回分数。"""
        zip_path = Path(zip_path)
        if not zip_path.exists():
            return Score(agent_name=agent_name, reason=f"代码包不存在: {zip_path}")

        files = self._read_zip(zip_path)
        key_files = PRODUCT_FILES.get(task.product_type, ["*"])

        # 静态检查：不调 LLM
        completeness = self._check_completeness(files, key_files)

        # 代码体量评分（文件数、总行数 — 给无 LLM 时提供区分度）
        total_lines = sum(c.count("\n") for c in files.values())
        file_count = len(files)
        heft_score = min(100, file_count * 10 + total_lines / 5)

        # AI 审查：调 LLM
        prompt = self._build_prompt(files, task)
        raw = self._call_llm(prompt)
        ai_scores = self._parse_scores(raw, heft_score)

        overall = round(
            0.25 * completeness +
            0.30 * ai_scores["functionality"] +
            0.25 * ai_scores["code_quality"] +
            0.20 * ai_scores["design"],
            1,
        )

        return Score(
            agent_name=agent_name or (task.name or "unknown"),
            completeness=round(completeness, 1),
            functionality=ai_scores["functionality"],
            code_quality=ai_scores["code_quality"],
            design=ai_scores["design"],
            overall=overall,
            reason=ai_scores["reason"],
            code_path=str(zip_path),
        )

    def rank(self, scores: list[Score]) -> list[Score]:
        """按总分降序排列。"""
        return sorted(scores, key=lambda s: s.overall, reverse=True)

    def compare(self, scores: list[Score]) -> str:
        """生成多者对比报告。"""
        ranked = self.rank(scores)
        lines = [f"🏆 竞技排名（共 {len(ranked)} 个参赛者）\n"]
        for i, s in enumerate(ranked, 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
            lines.append(
                f"  {medal} {s.agent_name}: {s.overall}分  "
                f"(完整度{s.completeness} 功能{s.functionality} "
                f"质量{s.code_quality} 设计{s.design})"
            )
        return "\n".join(lines)

    # ── 内部 ──

    def _read_zip(self, zip_path: Path) -> dict[str, str]:
        """解压并读取所有文本文件内容。"""
        files = {}
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for name in zf.namelist():
                    if name.startswith("__") or "/" in name:
                        continue
                    try:
                        content = zf.read(name).decode("utf-8", errors="replace")
                        files[name] = content[:MAX_FILE_BYTES]
                    except Exception:
                        continue
        except Exception:
            pass
        return files

    def _check_completeness(self, files: dict[str, str],
                             key_files: list[str]) -> float:
        """静态检查：关键文件齐全度。"""
        if key_files == ["*"]:
            return 80.0 if len(files) >= 2 else 40.0
        found = sum(1 for f in key_files if f in files)
        return round(found / len(key_files) * 100, 1)

    def _build_prompt(self, files: dict[str, str], task: ArenaTask) -> str:
        """构建发给 LLM 的评审 prompt。"""
        # 只发关键文件，控制上下文大小
        code_lines = []
        count = 0
        for name, content in files.items():
            if count >= MAX_FILES_TO_SHOW:
                break
            ext = name.rsplit(".", 1)[-1] if "." in name else ""
            code_lines.append(f"### {name}\n```{ext}\n{content[:MAX_FILE_BYTES]}\n```")
            count += 1

        code_section = "\n\n".join(code_lines) if code_lines else "(空代码包)"

        features = "\n".join(f"- {f}" for f in task.features) if task.features else "(未指定)"
        constraints = "\n".join(f"- {c}" for c in task.constraints) if task.constraints else "(无)"

        return f"""你是资深软件架构师和代码评审专家。请评审以下 AI 生成的代码。

## 用户需求
{task.description}

## 期望功能
{features}

## 约束条件
{constraints}

## 产品类型
{task.product_type}

## 代码文件
{code_section}

## 评审要求
从以下维度打分（0-100），并给出评审理由：

1. **functionality** — 代码是否实现了用户描述的功能？功能匹配度如何？
2. **code_quality** — 代码结构是否清晰？有无明显 bug、安全漏洞、冗余代码？
3. **design** — 界面设计是否美观？用户体验如何？（如无可视界面给 70）

请严格输出 JSON（不要额外文字）：
{{"functionality": <int>, "code_quality": <int>, "design": <int>, "reason": "<中文评审理由，控制在80字以内>"}}"""

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM（优先 DeepSeek，失败 fallback 模拟评分）。"""
        if self._api_key:
            try:
                return call_deepseek(
                    prompt, self._api_key, self._base_url,
                    temperature=0.2, max_tokens=600, timeout=45,
                )
            except Exception:
                pass
        return ""  # 空字符串触发 _parse_scores 的 fallback

    def _fallback_eval(self, prompt: str) -> str:
        """无 LLM 时的 fallback 评分。"""
        return '{"functionality": 60, "code_quality": 60, "design": 60, "reason": "未连接 LLM，使用默认评分"}'

    def _parse_scores(self, raw: str, heft_seed: float = 60) -> dict:
        """从 LLM 回复中提取评分 JSON。无 LLM 时基于代码特征给分。"""
        if raw:
            try:
                data = json.loads(extract_json(raw))
                return {
                    "functionality": self._clamp(data.get("functionality", 60)),
                    "code_quality": self._clamp(data.get("code_quality", 60)),
                    "design": self._clamp(data.get("design", 60)),
                    "reason": str(data.get("reason", ""))[:120],
                }
            except Exception:
                pass
        # 无 LLM：基于代码体量 + 微小随机扰动，给进化提供区分度
        import random
        base = self._clamp(heft_seed, 45, 85)
        return {
            "functionality": self._clamp(base + random.uniform(-8, 8)),
            "code_quality": self._clamp(base + random.uniform(-6, 6)),
            "design": self._clamp(base + random.uniform(-10, 10)),
            "reason": "LLM 未连接，基于代码体量自动评分",
        }

    @staticmethod
    def _clamp(v: float | int, lo: int = 0, hi: int = 100) -> float:
        return max(lo, min(hi, float(v)))
