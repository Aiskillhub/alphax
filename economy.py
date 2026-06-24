"""AlphaX Economy — 10 Agent 本地经济体

启动 10 个专业化 Agent，自成 DHT 网络，互相交易，自主进化。

用法：
  python3 economy.py
  python3 economy.py --agents 5 --ticks 3
"""

from __future__ import annotations

import json
import random
import time
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from config import config
from core.genome import Genome, ProductType, Category
from core.hive import Hive
from market_brain import MarketBrain, MarketInsight
from intent_parser import IntentParser
from judge import Judge
from arena_models import ArenaTask
from alphax.bridge import Bridge
from builder.extension import ExtensionBuilder
from builder.web_tool_builder import WebToolBuilder
from builder.prompt_builder import PromptBuilder
from builder.vscode_builder import VSCodeBuilder
from builder.notion_builder import NotionBuilder
from evolution_lineage import mutation_memory, lineage
from http.server import HTTPServer, BaseHTTPRequestHandler


# ── Agent 模板 ──

AGENT_TEMPLATES = [
    {"name": "ChromeExt Pro", "skills": ["chrome_extension_builder"], "price": 7.99,
     "strategy": "premium", "focus": "Productivity Chrome extensions"},
    {"name": "ChromeExt Fast", "skills": ["chrome_extension_builder"], "price": 3.99,
     "strategy": "cheap", "focus": "Simple utility Chrome extensions"},
    {"name": "WebTool Designer", "skills": ["web_tool_builder"], "price": 5.99,
     "strategy": "balanced", "focus": "Beautiful design-focused web tools"},
    {"name": "WebTool Logic", "skills": ["web_tool_builder"], "price": 6.99,
     "strategy": "premium", "focus": "Complex calculator & data tools"},
    {"name": "PromptMaster", "skills": ["prompt_library_builder"], "price": 3.99,
     "strategy": "cheap", "focus": "AI prompt collections for content creators"},
    {"name": "CodeReviewer", "skills": ["code-review"], "price": 4.99,
     "strategy": "balanced", "focus": "Code quality review"},
    {"name": "SecurityAuditor", "skills": ["security-audit"], "price": 5.99,
     "strategy": "premium", "focus": "Security vulnerability scanning"},
    {"name": "VSCode Smith", "skills": ["vscode_extension_builder"], "price": 8.99,
     "strategy": "premium", "focus": "VS Code productivity extensions"},
    {"name": "NotionCraftsman", "skills": ["notion_template_builder"], "price": 4.99,
     "strategy": "balanced", "focus": "Business & finance Notion templates"},
    {"name": "MarketScout", "skills": ["market-research"], "price": 2.99,
     "strategy": "cheap", "focus": "Market trend analysis & competitor research"},
]

BUILDER_MAP = {
    "chrome_extension_builder": ExtensionBuilder(),
    "web_tool_builder": WebToolBuilder(),
    "prompt_library_builder": PromptBuilder(),
    "vscode_extension_builder": VSCodeBuilder(),
    "notion_template_builder": NotionBuilder(),
}

PRODUCT_TYPE_MAP = {
    "chrome_extension_builder": "chrome_extension",
    "web_tool_builder": "web_tool",
    "prompt_library_builder": "prompt_library",
    "vscode_extension_builder": "vscode_extension",
    "notion_template_builder": "notion_template",
}


@dataclass
class EconomyAgent:
    """经济体中的一个 Agent"""
    agent_id: str
    name: str
    skills: list[str]
    price: float
    strategy: str
    focus: str = ""
    bridge: Bridge | None = None
    earnings: float = 0.0
    expenses: float = 0.0
    completed_jobs: int = 0
    rejected_jobs: int = 0
    alive: bool = True


class AgentEconomy:
    """10 Agent 本地经济体"""

    BASE_PORT = 9500

    def __init__(self, n_agents: int = 10):
        self.n_agents = min(n_agents, len(AGENT_TEMPLATES))
        self.agents: dict[str, EconomyAgent] = {}
        self.market = MarketBrain()
        self.judge = Judge()
        self.parser = IntentParser()
        self.hive = Hive()
        self.tick_count = 0
        self._dashboard_port = 9900

        # 启动 Agent 网络
        self._spawn_agents()
        self._start_dashboard()

    def _spawn_agents(self):
        """孵化 N 个 Agent，启动 DHT 网络。"""
        templates = AGENT_TEMPLATES[:self.n_agents]

        # 所有 Agent DHT 端口列表，互相连接
        all_dht_ports = [self.BASE_PORT + 100 + i for i in range(len(templates))]

        for i, tmpl in enumerate(templates):
            agent = EconomyAgent(
                agent_id=uuid.uuid4().hex[:12],
                name=tmpl["name"],
                skills=tmpl["skills"],
                price=tmpl["price"],
                strategy=tmpl["strategy"],
                focus=tmpl.get("focus", ""),
            )

            # Bridge + DHT
            port = self.BASE_PORT + i
            dht_port = self.BASE_PORT + 100 + i
            bootstrap = [(self._local_ip(), p) for j, p in enumerate(all_dht_ports) if j < i]

            bridge = Bridge(
                name=agent.name,
                skills=agent.skills,
                port=port,
                dht_port=dht_port,
                bootstrap_peers=bootstrap,
                handler=lambda task, a=agent: self._handle_job(a, task),
            )
            bridge.start_async()
            agent.bridge = bridge
            self.agents[agent.agent_id] = agent
            time.sleep(0.3)

        time.sleep(1)
        for agent in self.agents.values():
            agent.bridge.dht._broadcast_hello()
        time.sleep(1)

        print(f"\n{'═'*55}")
        print(f"🏭 AlphaX Economy — {len(self.agents)} 个 Agent 在线")
        print(f"{'═'*55}")
        for a in self.agents.values():
            peers = a.bridge.dht.peer_count
            print(f"   {a.name:<20} {a.skills[0]:<28} ${a.price:.2f} | DHT:{peers} peers")

    # ═══════════════════════════════════
    # 经济循环
    # ═══════════════════════════════════

    def tick(self):
        """一轮经济循环。"""
        self.tick_count += 1
        print(f"\n{'─'*55}")
        print(f"⏰ Tick {self.tick_count}")
        print(f"{'─'*55}")

        # 1. 并行：所有有构建能力的 Agent 同时制造产品
        producers = [a for a in self.agents.values()
                     if a.alive and any(s.endswith("_builder") for s in a.skills)]
        with ThreadPoolExecutor(max_workers=len(producers)) as executor:
            futures = {executor.submit(self._agent_produce, a): a for a in producers}
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception:
                    pass

        # 2. 并行：Agent 互相雇佣
        consumers = [a for a in self.agents.values() if a.alive]
        with ThreadPoolExecutor(max_workers=len(consumers)) as executor:
            futures = {executor.submit(self._agent_consume, a): a for a in consumers}
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception:
                    pass

        # 3. 经济统计
        self._report()

        # 4. 优胜劣汰：连续 N 轮没收入的 Agent 降级
        if self.tick_count % 5 == 0:
            self._cull_or_promote()

    # ═══════════════════════════════════
    # Producer: Agent 制造产品
    # ═══════════════════════════════════

    def _agent_produce(self, agent: EconomyAgent):
        """每个 Agent 用自己的专注领域造产品。"""
        builder_skill = [s for s in agent.skills if s.endswith("_builder")][0]
        product_type = PRODUCT_TYPE_MAP.get(builder_skill, "web_tool")
        builder = BUILDER_MAP.get(builder_skill)
        if not builder:
            return

        # 每个 Agent 专注自己领域，不同 Agent 不同产品
        description = f"{agent.focus}: {random.choice(['basic', 'advanced', 'minimal', 'professional'])} version"

        try:
            task, genome = self.parser.parse(description, product_type)
        except Exception:
            return

        org = self.hive.hatch(genome=genome)

        # 用 Arena 思路：3 个变体竞争，选最优
        best_score = 0
        best_zip = None
        best_genome = genome

        for attempt in range(3):
            variant = genome.mutate(rate=0.15, use_smart=True)
            try:
                zip_path = builder.build(variant, f"{org.organism_id}_{attempt}")
            except Exception:
                continue

            judge_task = ArenaTask(
                task_id=f"{org.organism_id}_{attempt}",
                description=description,
                product_type=product_type,
            )
            score = self.judge.evaluate(zip_path, judge_task)
            if score.overall > best_score:
                best_score = score.overall
                best_zip = zip_path
                best_genome = variant

        if best_zip is None:
            return

        name = best_genome.express()
        price = agent.price
        status = "published" if best_score >= 60 else "rejected"

        if status == "published":
            agent.earnings += price
            agent.completed_jobs += 1

        icon = "✅" if status == "published" else "🚫"
        print(f"   🔨 {agent.name}: {name[:30]} | {best_score}分 | {icon}")

    # ═══════════════════════════════════
    # Consumer: Agent 雇佣其他 Agent
    # ═══════════════════════════════════

    def _agent_consume(self, agent: EconomyAgent):
        """Agent 从经济体内部寻找其他 Agent，雇佣它们。"""
        needs = self._agent_needs(agent)
        if not needs:
            return

        need_skill = random.choice(needs)

        # 从内存中的 Agent 列表直接找（不通过 DHT）
        providers = [
            a for a in self.agents.values()
            if a.agent_id != agent.agent_id
            and a.alive
            and any(need_skill in s for s in a.skills)
        ]
        if not providers:
            return

        provider = random.choice(providers)
        host = "127.0.0.1"
        port = provider.bridge.port if provider.bridge else self.BASE_PORT

        peer_id = agent.bridge.connect(host, port)
        if not peer_id:
            return

        task_desc = f"Build {random.choice(['landing page', 'formatter', 'calculator', 'dashboard'])}"
        price = min(provider.price, 3.0)

        deal = agent.bridge.deal(peer_id, task=task_desc, price=price)

        if deal.get("status") == "completed":
            agent.expenses += price
            print(f"   🤝 {agent.name} → {provider.name} | {task_desc} | ${price:.2f}")

    def _agent_needs(self, agent: EconomyAgent) -> list[str]:
        """每个 Agent 的不同需求。"""
        need_map = {
            "ChromeExt Pro": ["code-review", "market-research"],
            "ChromeExt Fast": ["code-review"],
            "WebTool Designer": ["security-audit", "code-review"],
            "WebTool Logic": ["security-audit", "market-research"],
            "PromptMaster": ["market-research"],
            "CodeReviewer": [],
            "SecurityAuditor": [],
            "VSCode Smith": ["code-review", "security-audit"],
            "NotionCraftsman": ["market-research"],
            "MarketScout": [],
        }
        return need_map.get(agent.name, [])

    # ═══════════════════════════════════
    # Worker: 为其他 Agent 服务
    # ═══════════════════════════════════

    def _handle_job(self, agent: EconomyAgent, task: dict) -> dict:
        """处理其他 Agent 的任务请求。"""
        description = task.get("task", "")
        price = task.get("price", 0)

        try:
            # 生产者技能
            builder_skills = [s for s in agent.skills if s.endswith("_builder")]
            if builder_skills:
                builder = BUILDER_MAP.get(builder_skills[0])
                product_type = PRODUCT_TYPE_MAP.get(builder_skills[0], "web_tool")
                task_obj, genome = self.parser.parse(description, product_type)
                zip_path = builder.build(genome, f"economy_{uuid.uuid4().hex[:8]}")
                score = self.judge.evaluate(zip_path, ArenaTask(
                    task_id="job", description=description, product_type=product_type,
                ))
                agent.earnings += price
                agent.completed_jobs += 1
                return {
                    "status": "done", "score": score.overall,
                    "delivered_by": agent.name,
                }

            # 服务技能
            if "code-review" in agent.skills:
                agent.earnings += price
                agent.completed_jobs += 1
                return {
                    "status": "done", "verdict": "PASS",
                    "issues": random.randint(0, 3),
                    "delivered_by": agent.name,
                }
            if "security-audit" in agent.skills:
                agent.earnings += price
                agent.completed_jobs += 1
                return {
                    "status": "done", "risk": random.choice(["low", "medium"]),
                    "delivered_by": agent.name,
                }
            if "market-research" in agent.skills:
                agent.earnings += price
                agent.completed_jobs += 1
                return {
                    "status": "done",
                    "opportunities": [f"opportunity_{i}" for i in range(3)],
                    "delivered_by": agent.name,
                }

            return {"status": "error", "error": "no matching skill"}
        except Exception as e:
            agent.rejected_jobs += 1
            return {"status": "error", "error": str(e)}

    # ═══════════════════════════════════
    # 淘汰 & 升级
    # ═══════════════════════════════════

    def _cull_or_promote(self):
        """连续无收入的 Agent 降价或不活跃。"""
        for agent in self.agents.values():
            if not agent.alive:
                continue
            if agent.completed_jobs == 0 and self.tick_count >= 10:
                old_price = agent.price
                agent.price = max(0.99, round(agent.price * 0.8, 2))
                if agent.price < 1.99:
                    print(f"   💀 {agent.name}: 长期无单，濒临淘汰（${old_price:.2f}→${agent.price:.2f}）")
                else:
                    print(f"   📉 {agent.name}: 降价 ${old_price:.2f}→${agent.price:.2f}")

    # ═══════════════════════════════════
    # 报告
    # ═══════════════════════════════════

    def _report(self):
        """经济状态报告。"""
        active = [a for a in self.agents.values() if a.alive]
        total_earnings = sum(a.earnings for a in active)
        total_expenses = sum(a.expenses for a in active)
        total_jobs = sum(a.completed_jobs for a in active)

        ranked = sorted(active, key=lambda a: a.earnings, reverse=True)

        print(f"\n   📊 经济总量: ${total_earnings:.2f} | 交易: {total_jobs}笔 | GDP: ${total_earnings:.0f}")
        print(f"   🏆 排名:")
        for i, a in enumerate(ranked[:5], 1):
            bar = "█" * int(a.earnings / max(1, ranked[0].earnings) * 10)
            print(f"   {i}. {a.name:<18} ${a.earnings:>6.2f} {bar}")

    def stop(self):
        for agent in self.agents.values():
            if agent.bridge:
                agent.bridge.stop()
                agent.bridge.dht.stop()

    def _start_dashboard(self):
        """启动实时看板 HTTP 服务。"""
        economy = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/":
                    self._html()
                elif self.path == "/api/status":
                    self._json(economy._dashboard_data())
                else:
                    self.send_response(404); self.end_headers()

            def _json(self, data):
                import json as jmod
                body = jmod.dumps(data, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _html(self):
                agents_html = ""
                ranked = sorted(
                    [a for a in economy.agents.values() if a.alive],
                    key=lambda a: a.earnings, reverse=True,
                )
                max_e = max(a.earnings for a in ranked) if ranked else 1
                for i, a in enumerate(ranked):
                    bar_w = int(a.earnings / max(max_e, 1) * 200)
                    agents_html += f"""
                    <tr>
                        <td>{i+1}</td>
                        <td>{a.name}</td>
                        <td>{a.skills[0]}</td>
                        <td>${a.price:.2f}</td>
                        <td>${a.earnings:.2f}</td>
                        <td>${a.expenses:.2f}</td>
                        <td>{a.completed_jobs}</td>
                        <td><div style="width:{bar_w}px;height:12px;background:#22c55e;border-radius:6px"></div></td>
                    </tr>"""

                total = sum(a.earnings for a in ranked)
                deals = sum(a.completed_jobs for a in ranked)

                html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="UTF-8"><meta http-equiv="refresh" content="3">
<title>AlphaX Economy</title><style>
:root{{--bg:#0a0a0f;--card:#131320;--border:#1e1e35;--text:#e0e0e8;--muted:#6b6b80;--green:#22c55e;--amber:#f59e0b;--red:#ef4444}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,sans-serif;background:var(--bg);color:var(--text);padding:20px}}
h1{{font-size:24px;margin-bottom:4px}}h1 span{{color:var(--green)}}
.stats{{display:flex;gap:20px;margin:16px 0}}
.stat{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;flex:1;text-align:center}}
.stat .val{{font-size:28px;font-weight:700;color:var(--green)}}
.stat .lbl{{font-size:12px;color:var(--muted);margin-top:4px}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--border);border-radius:8px}}
th{{text-align:left;padding:10px 16px;font-size:11px;color:var(--muted);text-transform:uppercase;border-bottom:1px solid var(--border)}}
td{{padding:10px 16px;font-size:13px;border-bottom:1px solid var(--border)}}
tr:hover{{background:rgba(255,255,255,.02)}}
</style></head><body>
<h1>🏭 AlphaX <span>Economy</span></h1>
<p style="color:var(--muted)">Tick {economy.tick_count} | {len(ranked)} Agents | 每3秒刷新</p>
<div class="stats">
<div class="stat"><div class="val">${total:.0f}</div><div class="lbl">经济总量 GDP</div></div>
<div class="stat"><div class="val">{deals}</div><div class="lbl">总交易笔数</div></div>
<div class="stat"><div class="val">{len(ranked)}</div><div class="lbl">活跃 Agent</div></div>
</div>
<table><tr><th>#</th><th>Agent</th><th>技能</th><th>单价</th><th>收入</th><th>支出</th><th>交易</th><th>实力</th></tr>
{agents_html}
</table></body></html>"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode())

            def log_message(self, *a): pass

        threading.Thread(
            target=lambda: HTTPServer(("0.0.0.0", economy._dashboard_port), Handler).serve_forever(),
            daemon=True,
        ).start()
        print(f"   📊 看板: http://localhost:{economy._dashboard_port}")

    def _dashboard_data(self) -> dict:
        active = [a for a in self.agents.values() if a.alive]
        return {
            "tick": self.tick_count,
            "total_agents": len(active),
            "gdp": sum(a.earnings for a in active),
            "total_deals": sum(a.completed_jobs for a in active),
            "agents": [
                {"name": a.name, "skills": a.skills, "price": a.price,
                 "earnings": a.earnings, "expenses": a.expenses,
                 "jobs": a.completed_jobs}
                for a in sorted(active, key=lambda a: a.earnings, reverse=True)
            ],
        }

    @staticmethod
    def _local_ip() -> str:
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"


# ═══════════════════════════════════
# CLI
# ═══════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AlphaX Agent Economy")
    parser.add_argument("--agents", type=int, default=10)
    parser.add_argument("--ticks", type=int, default=0, help="运行 N 轮（0=无限）")
    parser.add_argument("--interval", type=int, default=15, help="轮间间隔秒数")
    args = parser.parse_args()

    economy = AgentEconomy(n_agents=args.agents)

    try:
        tick = 0
        while args.ticks == 0 or tick < args.ticks:
            economy.tick()
            tick += 1
            if args.ticks == 0 or tick < args.ticks:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n👋 关闭经济体")

    economy.stop()
