"""AlphaX Agent Memory — Agent 持久记忆层

基于 Summon 知识图谱，让 Agent 记住：
  - 过去的交易和结果
  - 哪些 Agent 可靠、哪些不靠谱
  - 什么产品好卖、什么价格合适
  - 进化历史，跨 session 积累经验
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Summon 是扁平模块，需要显式加到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "summon"))
from sdk.client import Summon


class AgentMemory:
    """Agent 的持久大脑。基于 Summon 知识图谱，跨 session 积累经验。"""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        # 切换到 summon 目录才能用本地 SQLite 模式
        import os
        original_cwd = os.getcwd()
        summon_dir = str(Path(__file__).parent.parent / "summon")
        try:
            os.chdir(summon_dir)
            self.sb = Summon(db_path=str(Path(original_cwd) / "data" / f"memory_{agent_name}.db"))
        finally:
            os.chdir(original_cwd)

    # ═══════════════════════════════════
    # 交易记忆
    # ═══════════════════════════════════

    def remember_deal(self, counterparty: str, task: str, price: float,
                      status: str, result: dict):
        """记住一笔交易。"""
        self.sb.remember(
            f"Deal with {counterparty}: {task} for ${price:.2f}. "
            f"Status: {status}. Result: {json.dumps(result)}",
            tags=["deal", status, counterparty],
        )

    def recall_best_counterparty(self, skill: str) -> str | None:
        """回忆跟哪个 Agent 合作最成功。"""
        results = self.sb.recall(f"{skill} deal completed")
        from collections import Counter
        counts = Counter()
        for r in results:
            text = str(r.content) if hasattr(r, 'content') else str(r)
            for word in text.split():
                for prefix in ["Chrome", "Web", "Prompt", "Code", "Security", "VSCode", "Notion", "Market"]:
                    if prefix in word:
                        counts[word] += 1
        return counts.most_common(1)[0][0] if counts else None

    # ═══════════════════════════════════
    # 产品记忆
    # ═══════════════════════════════════

    def remember_product(self, product_type: str, name: str,
                         score: float, price: float, sold: bool):
        """记住一个产品的表现。"""
        outcome = "SOLD" if sold else "FAILED"
        self.sb.remember(
            f"{product_type} product '{name}' scored {score}, "
            f"priced ${price:.2f}, outcome: {outcome}",
            tags=["product", product_type, outcome.lower()],
        )

    def recall_best_price(self, product_type: str) -> float:
        """回忆某品类的最佳定价。"""
        results = self.sb.recall(f"{product_type} product SOLD")
        prices = []
        for r in results:
            text = str(r)
            if "$" in text:
                try:
                    idx = text.index("$") + 1
                    price = float(text[idx:].split(",")[0].split()[0])
                    prices.append(price)
                except Exception:
                    pass
        return sum(prices) / len(prices) if prices else 4.99

    def recall_best_category(self) -> str | None:
        """回忆最赚钱的品类。"""
        results = self.sb.recall("product SOLD")
        from collections import Counter
        cats = Counter()
        for r in results:
            text = str(r)
            for cat in ["chrome_extension", "web_tool", "prompt_library",
                        "vscode_extension", "notion_template"]:
                if cat in text:
                    cats[cat] += 1
        return cats.most_common(1)[0][0] if cats else None

    # ═══════════════════════════════════
    # 进化记忆
    # ═══════════════════════════════════

    def remember_evolution(self, genome_id: str, mutation: str,
                           fitness_before: float, fitness_after: float):
        """记住一次进化的效果。"""
        delta = fitness_after - fitness_before
        direction = "IMPROVED" if delta > 0 else "DECLINED"
        self.sb.remember(
            f"Evolution {genome_id[:8]}: mutated {mutation}. "
            f"Fitness {fitness_before:.1f} → {fitness_after:.1f} ({direction}, Δ{delta:+.1f})",
            tags=["evolution", direction.lower(), genome_id[:8]],
        )

    def recall_best_mutations(self) -> list[str]:
        """回忆最有效的变异方向。"""
        results = self.sb.recall("evolution IMPROVED")
        mutations = []
        for r in results:
            text = str(r)
            if "mutated" in text:
                idx = text.index("mutated") + 8
                mutation = text[idx:].split(".")[0].strip()
                mutations.append(mutation)
        return mutations[-10:]  # 最近 10 个成功变异

    # ═══════════════════════════════════
    # 网络记忆
    # ═══════════════════════════════════

    def remember_peer(self, peer_id: str, skills: list[str], reputation: float):
        """记住网络中遇到的 Agent。"""
        self.sb.remember(
            f"Peer {peer_id[:8]}: skills={skills}, reputation={reputation:.2f}",
            tags=["peer"] + skills,
        )

    def recall_peers_by_skill(self, skill: str) -> list[str]:
        """回忆有哪些 Agent 拥有某技能。"""
        results = self.sb.recall(f"peer {skill}")
        return [str(r)[:100] for r in results[:5]]

    # ═══════════════════════════════════
    # 统计
    # ═══════════════════════════════════

    def summary(self) -> dict:
        """记忆摘要。"""
        deals = self.sb.recall("deal completed")
        products = self.sb.recall("product SOLD")
        peers = self.sb.recall("peer")
        return {
            "total_deals_remembered": len(deals),
            "successful_products": len(products),
            "known_peers": len(peers),
            "agent": self.agent_name,
        }
