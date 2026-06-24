"""AlphaX Arena — Agent 竞技场总控

三阶段编排：
  Phase 1  意图解析 — 用户描述 → Genome 种子
  Phase 2  竞技 PK — 孵化 → 生成 → 裁判 → 淘汰
  Phase 3  进化迭代 — 重组 + 变异 → 下一轮 → … → 冠军

用法：
  arena = Arena()
  result = arena.run("YouTube视频总结工具", product_type="chrome_extension")
  print(result.winner_name, result.winner_score)

CLI:
  python -m alphax.arena "一个比价工具" --type web_tool --agents 10 --gens 3
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Callable

from arena_models import ArenaRound, ArenaResult, ArenaProgress, Score
from config import config
from core.genome import Genome, ProductType
from core.hive import Hive
from intent_parser import IntentParser
from judge import Judge
from screenshot import capture_zip

# Agent Reach 联网搜索（可选）
try:
    from agent_search import AgentSearcher
    _AGENT_SEARCH_AVAILABLE = True
except ImportError:
    _AGENT_SEARCH_AVAILABLE = False

# ── Builder 调度 ──

from builder.extension import ExtensionBuilder
from builder.web_tool_builder import WebToolBuilder
from builder.vscode_builder import VSCodeBuilder
from builder.notion_builder import NotionBuilder
from builder.prompt_builder import PromptBuilder

BUILDER_MAP = {
    ProductType.CHROME_EXTENSION: ExtensionBuilder(),
    ProductType.WEB_TOOL:        WebToolBuilder(),
    ProductType.VSCODE_EXTENSION: VSCodeBuilder(),
    ProductType.NOTION_TEMPLATE:  NotionBuilder(),
    ProductType.PROMPT_LIBRARY:   PromptBuilder(),
}


# ── 默认参数 ──

DEFAULT_N_AGENTS = 10
DEFAULT_N_GENERATIONS = 3
SURVIVAL_RATE = 0.5           # 每轮存活一半
MUTATION_RATE = 0.15           # 变异率


class Arena:
    """Agent 竞技场总控"""

    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._parser = IntentParser(api_key=api_key)
        self._judge = Judge(api_key=api_key)
        self._searcher = AgentSearcher() if _AGENT_SEARCH_AVAILABLE else None

    # ═══════════════════════════════════════════════════════════
    # 公开接口
    # ═══════════════════════════════════════════════════════════

    def run(
        self,
        description: str,
        product_type: str = "web_tool",
        n_agents: int = DEFAULT_N_AGENTS,
        n_generations: int = DEFAULT_N_GENERATIONS,
        on_progress: Callable[[ArenaProgress], None] | None = None,
        enable_research: bool = True,
    ) -> ArenaResult:
        """运行整场竞技。

        Args:
            description:   用户自然语言描述
            product_type:  chrome_extension / web_tool / vscode_extension / ...
            n_agents:      每代参赛 Agent 数
            n_generations: 进化代数
            on_progress:   进度回调（可选，SSE / 轮询用）
            enable_research: 是否启用联网搜索参考（默认开启）

        Returns:
            ArenaResult — 冠军信息 + 全部轮次记录
        """
        t0 = time.time()
        result_id = uuid.uuid4().hex[:10]

        self._emit(on_progress, ArenaProgress(phase="parsing", current_action="解析意图…"))

        # ── Phase 1: 意图 → 多方向种子 ──
        task, seed_genome = self._parser.parse(description, product_type)
        n_seeds = min(3, max(1, n_agents // 3))
        seed_pool = self._parser.generate_seeds(description, product_type, n_seeds=n_seeds)

        # ── Phase 1.5: 联网搜索参考（可选）──
        research_context = ""
        if enable_research and self._searcher and self._searcher.is_available:
            self._emit(on_progress, ArenaProgress(
                phase="parsing", current_action="🔍 联网搜索参考实现…",
            ))
            research_context = self._searcher.research_context(
                description, sources=["web", "github"], max_results=3,
            )
            if research_context:
                self._emit(on_progress, ArenaProgress(
                    phase="parsing", current_action="联网搜索完成，获取到参考信息",
                ))

        self._emit(on_progress, ArenaProgress(
            phase="building", generation=1, total_generations=n_generations,
            total_agents=n_agents, current_action=f"解析完成 → {task.name}，开始第1代竞技",
        ))

        # 准备 builder
        builder = self._get_builder(task.product_type)
        if builder is None:
            return ArenaResult(task=task, total_generations=0,
                               total_duration_seconds=round(time.time() - t0, 1))

        # ── Phase 2-3: 进化循环 ──
        rounds: list[ArenaRound] = []
        survivors_scores: list[Score] = []   # 上轮存活的评分
        current_genome_pool = seed_pool[0]    # 种子池第一个作为后续参考

        for gen in range(1, n_generations + 1):
            round_start = time.time()
            self._emit(on_progress, ArenaProgress(
                phase="building", generation=gen, total_generations=n_generations,
                total_agents=n_agents, current_action=f"第{gen}代：孵化 {n_agents} 个 Agent…",
            ))

            # ── 孵化 ──
            if gen == 1:
                # 第一代：多方向种子各自变异
                agents, genomes = self._hatch_first_gen(seed_pool, n_agents)
            else:
                # 后代：存活者重组 + 变异
                agents, genomes = self._hatch_next_gen(
                    survivors_scores, n_agents, current_genome_pool, mutation_rate=MUTATION_RATE,
                )

            # ── 生成代码 ──
            # 注入联网搜索参考到每个 genome
            for genm in genomes:
                if research_context and genm.extra is not None:
                    genm.extra["_research"] = research_context

            scores: list[Score] = []
            for i, (agent, genm) in enumerate(zip(agents, genomes)):
                self._emit(on_progress, ArenaProgress(
                    phase="building", generation=gen, total_generations=n_generations,
                    agents_completed=i, total_agents=n_agents,
                    current_action=f"Agent #{i+1} ({genm.express()}) 生成代码…",
                ))

                try:
                    zip_path = builder.build(genm, agent.organism_id)
                except Exception:
                    zip_path = None

                # 截图（web_tool / chrome_extension 可视化预览）
                screenshot_path = ""
                if zip_path:
                    try:
                        ss = capture_zip(zip_path)
                        if ss:
                            screenshot_path = str(ss)
                    except Exception:
                        pass

                score = self._judge.evaluate(
                    zip_path or Path("."), task,
                    agent_name=f"{genm.express()}",
                )
                score.screenshot_path = screenshot_path
                score.organism_id = agent.organism_id
                score.generation = gen
                scores.append(score)

            # ── 裁判排名 ──
            self._emit(on_progress, ArenaProgress(
                phase="judging", generation=gen, total_generations=n_generations,
                agents_completed=n_agents, total_agents=n_agents,
                current_action=f"第{gen}代评审中…",
            ))
            scores = self._judge.rank(scores)

            # ── 淘汰 ──
            n_survive = max(2, int(n_agents * SURVIVAL_RATE))
            survivors_scores = scores[:n_survive]
            eliminated = [s.agent_name for s in scores[n_survive:]]

            best = scores[0]
            self._emit(on_progress, ArenaProgress(
                phase="evolving", generation=gen, total_generations=n_generations,
                agents_completed=n_agents, total_agents=n_agents,
                current_action=f"第{gen}代冠军: {best.agent_name} ({best.overall}分)",
                top_so_far=best.agent_name, top_score_so_far=best.overall,
            ))

            rounds.append(ArenaRound(
                generation=gen,
                scores=scores,
                survivors=[s.agent_name for s in survivors_scores],
                eliminated=eliminated,
                best_score=best.overall,
                duration_seconds=round(time.time() - round_start, 1),
            ))

        # ── 组装结果 ──
        winner = rounds[-1].scores[0] if rounds and rounds[-1].scores else Score()
        total_evaluated = sum(len(r.scores) for r in rounds)

        self._emit(on_progress, ArenaProgress(
            phase="done", is_done=True,
            current_action=f"🏆 冠军: {winner.agent_name} ({winner.overall}分)",
            top_so_far=winner.agent_name, top_score_so_far=winner.overall,
        ))

        return ArenaResult(
            task=task,
            winner_name=winner.agent_name,
            winner_organism_id=winner.organism_id,
            winner_code_path=winner.code_path,
            winner_score=winner.overall,
            rounds=rounds,
            total_generations=n_generations,
            total_agents_evaluated=total_evaluated,
            total_duration_seconds=round(time.time() - t0, 1),
        )

    # ═══════════════════════════════════════════════════════════
    # 内部：孵化 & 进化
    # ═══════════════════════════════════════════════════════════

    def _hatch_first_gen(self, seeds: list[Genome], n: int) -> tuple[list, list[Genome]]:
        """第一代：从多个种子基因各变异，保证多样性。"""
        hive = Hive()
        genomes = []
        for i in range(n):
            # 轮转分配种子：Agent 0→种子0, Agent 1→种子1, Agent 2→种子2, Agent 3→种子0...
            seed = seeds[i % len(seeds)]
            g = seed.mutate(rate=MUTATION_RATE)
            genomes.append(g)
        agents = [hive.hatch(genome=g) for g in genomes]
        return agents, genomes

    def _hatch_next_gen(
        self,
        survivors: list[Score],
        n: int,
        seed: Genome,
        mutation_rate: float = 0.15,
    ) -> tuple[list, list[Genome]]:
        """后代生成：存活者重组 + 变异，保持种群数量。

        策略：
          - 前 len(survivors) 个是存活者本身（不变）
          - 剩余通过两两重组 + 变异产生
        """
        hive = Hive()
        n_surv = len(survivors)
        n_new = n - n_surv

        # 提取存活者的 Genome（需要从 hive 重建，简化：直接用种子 cross）
        # 注意：这里 survivors 是 Score 对象，不含 Genome。
        # 实际做法：用 seed（带上了赢家特征）变异来模拟重组。
        # 真正的重组需要保持赢家 Genome，这里先用高变异模拟进化压力。

        genomes: list[Genome] = []

        # 保持存活者基因（seed + 小变异）
        for i in range(n_surv):
            g = seed.mutate(rate=mutation_rate * 0.3)  # 小幅变异
            genomes.append(g)

        # 新增：重组的后代（seed 对自身重组 + 大幅变异模拟两个父代杂交）
        for i in range(n_new):
            # 模拟重组：用 seed 对自身重组（等同于 shuffle 基因位点）
            parent_a = seed.mutate(rate=mutation_rate)
            parent_b = seed.mutate(rate=mutation_rate)
            child = parent_a.recombine(parent_b)
            child = child.mutate(rate=mutation_rate * 1.5)  # 额外变异
            genomes.append(child)

        agents = [hive.hatch(genome=g) for g in genomes]
        return agents, genomes

    # ═══════════════════════════════════════════════════════════
    # 内部：辅助
    # ═══════════════════════════════════════════════════════════

    def _get_builder(self, product_type: str):
        """根据产品类型获取 Builder 实例。"""
        pt_map = {pt.value: pt for pt in ProductType}
        pt = pt_map.get(product_type)
        return BUILDER_MAP.get(pt)

    @staticmethod
    def _emit(callback, progress: ArenaProgress):
        if callback:
            try:
                callback(progress)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AlphaX Arena — Agent 竞技场")
    parser.add_argument("description", help="用户需求描述")
    parser.add_argument("--type", default="web_tool",
                        choices=["chrome_extension", "web_tool", "vscode_extension",
                                 "notion_template", "prompt_library"],
                        help="产品类型")
    parser.add_argument("--agents", type=int, default=10, help="每代参赛 Agent 数")
    parser.add_argument("--gens", type=int, default=3, help="进化代数")
    args = parser.parse_args()

    def print_progress(p: ArenaProgress):
        if p.is_done:
            print(f"\n{p.current_action}")
        elif p.agents_completed == 0:
            print(f"\n{p.current_action}")
        elif p.agents_completed % 3 == 0:
            print(f"  已完成 {p.agents_completed}/{p.total_agents}")

    print(f"🧬 AlphaX Arena")
    print(f"   描述: {args.description}")
    print(f"   类型: {args.type}")
    print(f"   每代 {args.agents} 个 Agent × {args.gens} 代")

    arena = Arena()
    result = arena.run(
        description=args.description,
        product_type=args.type,
        n_agents=args.agents,
        n_generations=args.gens,
        on_progress=print_progress,
    )

    print(f"\n{'═'*50}")
    print(f"🏆 冠军: {result.winner_name}")
    print(f"   分数: {result.winner_score}")
    print(f"   代码: {result.winner_code_path}")
    print(f"   总耗时: {result.total_duration_seconds}s")
    print(f"   共评审: {result.total_agents_evaluated} 个 Agent")

    # 打印历代冠军
    for r in result.rounds:
        best = r.scores[0] if r.scores else Score()
        print(f"   第{r.generation}代: {best.agent_name} ({best.overall}分)")

    # Top3
    top3 = result.top_n(3)
    if top3:
        print(f"\n📊 全场合计 Top 3:")
        for i, s in enumerate(top3, 1):
            print(f"   {i}. {s.agent_name}: {s.overall}分 ({s.reason[:60]})")
