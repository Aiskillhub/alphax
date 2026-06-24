"""AlphaX Arena — 数据模型

Arena 竞技系统的所有数据结构。
三个新模块（intent_parser / judge / arena）共享这些类型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.genome import Genome


# ── 意图解析结果 ──

@dataclass
class ArenaTask:
    """一次解析后的竞技任务"""
    task_id: str
    description: str               # 用户原始描述
    product_type: str               # chrome_extension / web_tool / ...
    name: str = ""                  # 解析出的产品名
    features: list[str] = field(default_factory=list)
    design_style: str = "minimal"   # UI 风格
    target_market: str = "english"
    constraints: list[str] = field(default_factory=list)  # "性能<500ms"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── 评审分数 ──

@dataclass
class Score:
    """一次评审结果（0-100 每维）"""
    agent_name: str = ""
    organism_id: str = ""
    completeness: float = 0.0       # 代码完整度：文件齐不齐
    functionality: float = 0.0      # 功能匹配度：跟需求对不对得上
    code_quality: float = 0.0       # 代码质量：结构、可读性、bug
    design: float = 0.0             # UI/UX 设计分
    overall: float = 0.0            # 加权总分
    reason: str = ""                # 裁判评语
    code_path: str = ""             # zip 包路径
    screenshot_path: str = ""       # 截图路径
    generation: int = 0


# ── 竞技轮次 ──

@dataclass
class ArenaRound:
    """一轮竞技（一代）的结果"""
    generation: int
    scores: list[Score] = field(default_factory=list)
    survivors: list[str] = field(default_factory=list)   # 存活的 agent 名
    eliminated: list[str] = field(default_factory=list)  # 淘汰的 agent 名
    best_score: float = 0.0
    duration_seconds: float = 0.0


# ── 最终结果 ──

@dataclass
class ArenaResult:
    """整场竞技的最终输出"""
    task: ArenaTask | None = None
    winner_name: str = ""
    winner_organism_id: str = ""
    winner_code_path: str = ""      # 冠军代码 zip 路径
    winner_score: float = 0.0
    rounds: list[ArenaRound] = field(default_factory=list)
    total_generations: int = 3
    total_agents_evaluated: int = 0
    total_duration_seconds: float = 0.0

    def top_n(self, n: int = 3) -> list[Score]:
        """返回全场合计 top N"""
        all_scores = []
        for r in self.rounds:
            all_scores.extend(r.scores)
        all_scores.sort(key=lambda s: s.overall, reverse=True)
        return all_scores[:n]


# ── 进度推送 ──

@dataclass
class ArenaProgress:
    """实时进度，推给前端轮询"""
    phase: str = "idle"             # parsing | building | judging | evolving | done
    generation: int = 0
    total_generations: int = 3
    agents_completed: int = 0
    total_agents: int = 10
    current_action: str = ""        # "Agent #3 正在生成代码…"
    top_so_far: str = ""            # 当前最高分 Agent 名
    top_score_so_far: float = 0.0
    is_done: bool = False
    error: str = ""
