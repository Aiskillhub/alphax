"""AlphaX Agent Node — 自主 Agent 经济节点

一个完整的 Agent 经济参与者：
  1. 自主赚钱（造产品 → 上架 → 卖给人）
  2. 加入 A2A 网络（其他 Agent 可以雇佣它）
  3. 雇佣其他 Agent（外包自己做不了的事）

启动：
  python3 agent_node.py                    # 单节点
  python3 agent_node.py --port 9101        # 指定端口
  python3 agent_node.py --peer 127.0.0.1:9103  # 加入已有网络
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from config import config
from core.genome import Genome, SEED_GENOMES, ProductType
from core.hive import Hive
from market_brain import MarketBrain
from intent_parser import IntentParser
from judge import Judge
from arena_models import ArenaTask
from alphax.bridge import Bridge
from dht import DHTNode

# Builders
from builder.extension import ExtensionBuilder
from builder.web_tool_builder import WebToolBuilder
from builder.prompt_builder import PromptBuilder


class AgentNode:
    """一个自主 AI 经济节点。

    同时具备三种能力：
    - Producer: 自主造产品卖钱
    - Worker:  为其他 Agent 提供构建服务
    - Consumer: 雇佣其他 Agent 做事
    """

    def __init__(self, name: str = "AlphaX Node",
                 port: int = 9101, dht_port: int = 0,
                 bootstrap_peers: list[tuple[str, int]] | None = None):
        self.name = name
        self.node_id = uuid.uuid4().hex[:12]

        # ── 能力注册 ──
        self.skills = [
            "web_tool_builder",
            "chrome_extension_builder",
            "prompt_library_builder",
            "code-review",
            "market-research",
        ]

        # ── A2A Bridge ──
        self.bridge = Bridge(
            name=name,
            skills=self.skills,
            port=port,
            dht_port=dht_port,
            bootstrap_peers=bootstrap_peers or [],
            handler=self._handle_job,
        )

        # ── 自主赚钱 ──
        self.market = MarketBrain()
        self.parser = IntentParser()
        self.judge = Judge()
        self.hive = Hive()
        self.ext_builder = ExtensionBuilder()
        self.web_builder = WebToolBuilder()
        self.prompt_builder = PromptBuilder()

        # ── 产品 & 交易记录 ──
        self.products: dict[str, dict] = {}
        self.deals_completed: list[dict] = []
        self.earnings_human: float = 0.0    # 卖产品赚的
        self.earnings_agent: float = 0.0    # Agent 雇佣赚的

        # ── 状态 ──
        self._running = False

    # ═══════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════

    def start(self):
        """启动 Agent 节点。加入网络，开始自主运作。"""
        self._running = True
        self.bridge.start_async()
        time.sleep(2)

        print(f"\n{'═'*55}")
        print(f"🤖 {self.name}")
        print(f"   ID: {self.node_id}")
        print(f"   Skills: {', '.join(self.skills)}")
        print(f"   Bridge: port {self.bridge.port}")
        print(f"   DHT: {self.bridge.dht.peer_count} peers")
        print(f"{'═'*55}\n")

        # 主循环
        while self._running:
            self._tick()
            time.sleep(30)  # 30s 一轮（生产环境改 3600）

    def stop(self):
        self._running = False
        self.bridge.stop()
        self.bridge.dht.stop()

    # ═══════════════════════════════════
    # 自主循环
    # ═══════════════════════════════════

    def _tick(self):
        """一轮自主循环。"""
        # 1. 看看网络里有什么 Agent
        peers = self.bridge.dht.peer_list
        if len(peers) > 0:
            print(f"🌐 网络: {len(peers)} 个已知 Agent")

        # 2. 市场研究 → 造产品
        insights = self.market.research_opportunities(n=2)
        for ins in insights[:1]:  # 每轮只做一个
            self._produce(ins)

        # 3. 如果有需要的服务，雇佣其他 Agent
        self._outsource_if_needed()

        # 4. 报告
        total = self.earnings_human + self.earnings_agent
        if total > 0:
            print(f"💰 累计收入: ${total:.2f} (人:{self.earnings_human:.0f} Agent:{self.earnings_agent:.0f})")

    # ═══════════════════════════════════
    # Producer: 自主造产品
    # ═══════════════════════════════════

    def _produce(self, insight):
        """从市场洞察生成一个产品。"""
        print(f"   🔨 制造: {insight.keyword}")

        try:
            task, genome = self.parser.parse(insight.keyword, insight.category)
        except Exception:
            genome = SEED_GENOMES[0].mutate()

        org = self.hive.hatch(genome=genome)

        # 构建
        try:
            pt = genome.product_type.value
            if pt == "chrome_extension":
                zip_path = self.ext_builder.build(genome, org.organism_id)
            elif pt == "prompt_library":
                zip_path = self.prompt_builder.build(genome, org.organism_id)
            else:
                zip_path = self.web_builder.build(genome, org.organism_id)
        except Exception:
            return

        # 质量审查
        judge_task = ArenaTask(
            task_id=org.organism_id[:8],
            description=insight.keyword,
            product_type=pt,
        )
        score = self.judge.evaluate(zip_path, judge_task)

        name = genome.express()
        pid = uuid.uuid4().hex[:10]
        self.products[pid] = {
            "id": pid, "name": name, "type": pt,
            "genome_id": genome.genome_id,
            "score": score.overall, "price": genome.price_point,
            "status": "listed" if score.overall >= 60 else "rejected",
        }

        if score.overall >= 60:
            print(f"      ✅ {name} | {score.overall}分 | ${genome.price_point:.2f}")
        else:
            print(f"      🚫 {name} | {score.overall}分 不合格")

    # ═══════════════════════════════════
    # Worker: 为其他 Agent 提供服务
    # ═══════════════════════════════════

    def _handle_job(self, task: dict) -> dict:
        """响应其他 Agent 的任务请求。"""
        description = task.get("task", "")
        price = task.get("price", 0)

        print(f"   📩 收到任务: {description[:50]}... (${price:.2f})")

        # 用 arena 生成最优方案（简版：单次生成）
        try:
            task_obj, genome = self.parser.parse(description)
            pt = genome.product_type.value

            if pt == "web_tool":
                zip_path = self.web_builder.build(genome, f"job_{uuid.uuid4().hex[:8]}")
            elif pt == "chrome_extension":
                zip_path = self.ext_builder.build(genome, f"job_{uuid.uuid4().hex[:8]}")
            else:
                zip_path = self.web_builder.build(genome, f"job_{uuid.uuid4().hex[:8]}")

            score = self.judge.evaluate(zip_path, ArenaTask(
                task_id="job", description=description, product_type=pt,
            ))

            self.earnings_agent += price
            self.deals_completed.append({
                "task": description[:60], "price": price, "score": score.overall,
            })

            return {
                "status": "done",
                "product_name": genome.express(),
                "score": score.overall,
                "delivered_by": self.name,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ═══════════════════════════════════
    # Consumer: 雇佣其他 Agent
    # ═══════════════════════════════════

    def _outsource_if_needed(self):
        """如果自己不会的，找网络上其他 Agent 做。"""
        # 例：需要安全审计，自己没有
        need_audit = any(p.get("status") == "listed" and p.get("score", 0) > 80
                         for p in self.products.values())

        if need_audit:
            auditors = self.bridge.discover("security-audit")
            if auditors:
                auditor = auditors[0]
                host = auditor.get("host", "127.0.0.1")
                port = auditor.get("port", 9101)

                peer_id = self.bridge.connect(host, port)
                if peer_id:
                    deal = self.bridge.deal(
                        peer_id,
                        task="Security audit for newly generated web tools",
                        price=2.00,
                    )
                    if deal.get("status") == "completed":
                        print(f"   🛡️ 安全审计完成: {deal.get('work_result', {})}")


# ═══════════════════════════════════
# CLI
# ═══════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AlphaX Agent Node")
    parser.add_argument("--port", type=int, default=9101)
    parser.add_argument("--dht-port", type=int, default=0)
    parser.add_argument("--peer", action="append", help="Bootstrap peer host:port")
    parser.add_argument("--name", default="AlphaX Node")
    args = parser.parse_args()

    bootstrap = []
    if args.peer:
        for p in args.peer:
            host, port = p.split(":")
            bootstrap.append((host, int(port)))

    node = AgentNode(
        name=args.name,
        port=args.port,
        dht_port=args.dht_port or args.port + 100,
        bootstrap_peers=bootstrap,
    )

    try:
        node.start()
    except KeyboardInterrupt:
        print("\n👋 关闭")
        node.stop()
