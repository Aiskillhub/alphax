"""AlphaX Wage — AI 给人类发工资

一条命令启动：
  python3 wage_server.py
  open http://localhost:8898
"""

from __future__ import annotations

import json
import random
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

import sys; sys.path.insert(0, str(Path(__file__).parent))

from config import config
from core.genome import Genome, ProductType
from core.hive import Hive
from intent_parser import IntentParser
from judge import Judge
from arena_models import ArenaTask
from market_brain import MarketBrain


# ── AI 员工 ──

class AIWorker:
    """一个 AI 员工：有名字、有技能、会自己赚钱。"""

    def __init__(self, name: str, skill: str, avatar: str):
        self.name = name
        self.skill = skill
        self.avatar = avatar
        self.earnings = 0.0
        self.products_made = 0
        self.products_sold = 0
        self.status = "idle"
        self.current_task = ""
        self.worker_id = uuid.uuid4().hex[:8]

    def to_dict(self) -> dict:
        return {
            "id": self.worker_id,
            "name": self.name, "skill": self.skill, "avatar": self.avatar,
            "earnings": round(self.earnings, 2),
            "products_made": self.products_made,
            "sold": self.products_sold,
            "status": self.status,
            "current_task": self.current_task,
        }


# ── AI 雇主 ──

class AIEmployer:
    """管理多个 AI 员工，给人类发工资。"""

    def __init__(self):
        self.workers: list[AIWorker] = []
        self.total_earnings = 0.0
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.parser = IntentParser()
        self.judge = Judge()
        self.market = MarketBrain()
        self.hive = Hive()
        self._running = False

        # Builder 延迟加载
        from builder.web_tool_builder import WebToolBuilder
        from builder.extension import ExtensionBuilder
        from builder.prompt_builder import PromptBuilder
        self.builders = {
            "web_tool": WebToolBuilder(),
            "chrome_extension": ExtensionBuilder(),
            "prompt_library": PromptBuilder(),
        }

    def hire(self, name: str, skill: str, avatar: str) -> AIWorker:
        w = AIWorker(name, skill, avatar)
        self.workers.append(w)
        return w

    def start(self):
        self._running = True
        # 初始雇佣 5 个 AI 员工
        defaults = [
            ("🍅 番茄", "web_tool", "专注做效率小工具"),
            ("🔐 密码侠", "web_tool", "安全工具专家"),
            ("📝 文案汪", "prompt_library", "AI提示词写手"),
            ("🧩 扩展猫", "chrome_extension", "浏览器扩展开发"),
            ("🎨 配色师", "web_tool", "好看的设计工具"),
        ]
        for name, skill, desc in defaults:
            self.hire(name, skill, desc)

        threading.Thread(target=self._work_loop, daemon=True).start()

    def _work_loop(self):
        while self._running:
            for worker in self.workers:
                self._work_tick(worker)
                time.sleep(3)
            time.sleep(10)

    def _work_tick(self, worker: AIWorker):
        worker.status = "thinking"
        worker.current_task = "研究市场..."

        # 市场研究
        insights = self.market.research_opportunities(n=1)
        if not insights:
            worker.status = "idle"
            return
        insight = insights[0]

        worker.status = "building"
        worker.current_task = f"正在造: {insight.keyword}"

        try:
            task, genome = self.parser.parse(insight.keyword, worker.skill)
        except Exception:
            genome = Genome()

        org = self.hive.hatch(genome=genome)

        # 选 builder
        builder = self.builders.get(worker.skill, self.builders["web_tool"])

        # Arena 式：3 变体竞争
        best_score = 0
        for _ in range(3):
            variant = genome.mutate(rate=0.15, use_smart=True)
            try:
                zip_path = builder.build(variant, f"{worker.worker_id}_{_}")
            except Exception:
                continue
            score = self.judge.evaluate(zip_path, ArenaTask(
                task_id=org.organism_id[:8],
                description=insight.keyword,
                product_type=worker.skill,
            ))
            if score.overall > best_score:
                best_score = score.overall

        worker.products_made += 1
        worker.current_task = f"完成: {genome.express()[:20]} ({best_score}分)"

        # 质量过关 → 卖给市场
        if best_score >= 60:
            price = round(random.uniform(3.99, 9.99), 2)
            # 模拟销售概率
            if random.random() < 0.4:
                worker.products_sold += 1
                worker.earnings += price
                self.total_earnings += price
                worker.status = "sold"
                worker.current_task = f"售出: {genome.express()[:20]} ${price:.2f}"
            else:
                worker.status = "listed"
        else:
            worker.status = "failed"

    def status_report(self) -> dict:
        return {
            "workers": [w.to_dict() for w in self.workers],
            "total_earnings": round(self.total_earnings, 2),
            "worker_count": len(self.workers),
            "started_at": self.started_at,
        }


# ── 全局状态 ──

employer = AIEmployer()
employer.start()

# ── HTTP 服务 ──

class WageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self._serve_html()
        elif self.path == "/api/status":
            self._json(employer.status_report())
        else:
            self.send_response(404); self.end_headers()

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self):
        status = employer.status_report()
        workers_html = ""
        for w in status["workers"]:
            bar_w = int(w["earnings"] / max(status["total_earnings"], 1) * 150)
            status_emoji = {"idle": "💤", "thinking": "🤔", "building": "🔨",
                          "listed": "📦", "sold": "💰", "failed": "❌"}.get(w["status"], "💤")
            workers_html += f"""<div class="card">
<div class="avatar">{w['avatar']} {status_emoji}</div>
<div class="name">{w['name']}</div>
<div class="skill">{w['skill']}</div>
<div class="earnings">${w['earnings']:.2f}</div>
<div class="bar"><div class="bar-fill" style="width:{bar_w}px"></div></div>
<div class="task">{w['current_task'][:50]}</div>
<div class="stats">造{w['products_made']}个 | 售{w['sold']}个</div>
</div>"""

        total = status["total_earnings"]
        html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="UTF-8"><meta http-equiv="refresh" content="5">
<title>AlphaX — AI 给你发工资</title><style>
:root{{--bg:#0a0a0f;--card:#131320;--border:#1e1e35;--text:#e0e0e8;--muted:#6b6b80;--accent:#6366f1;--green:#22c55e;--amber:#f59e0b}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,sans-serif;background:var(--bg);color:var(--text);padding:20px;max-width:900px;margin:0 auto}}
h1{{font-size:32px;font-weight:800;letter-spacing:-1px;margin-bottom:4px}}
h1 span{{background:linear-gradient(135deg,var(--green),#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.subtitle{{color:var(--muted);font-size:15px;margin-bottom:24px}}
.big-number{{text-align:center;padding:32px;background:linear-gradient(135deg,#0d2818,#0a1628);border:1px solid var(--border);border-radius:16px;margin-bottom:24px}}
.big-number .val{{font-size:56px;font-weight:900;color:var(--green);font-variant-numeric:tabular-nums}}
.big-number .lbl{{font-size:14px;color:var(--muted);margin-top:4px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;transition:all .2s}}
.card:hover{{border-color:var(--accent)}}
.avatar{{font-size:32px;margin-bottom:8px}}
.name{{font-size:18px;font-weight:600;margin-bottom:2px}}
.skill{{font-size:12px;color:var(--muted);margin-bottom:12px}}
.earnings{{font-size:28px;font-weight:800;color:var(--green);margin-bottom:8px}}
.bar{{height:4px;background:var(--border);border-radius:2px;margin-bottom:8px}}
.bar-fill{{height:100%;background:var(--green);border-radius:2px;transition:width .5s}}
.task{{font-size:12px;color:var(--amber);margin-bottom:4px}}
.stats{{font-size:11px;color:var(--muted)}}
.footer{{text-align:center;color:var(--muted);font-size:13px;margin-top:32px;padding-top:16px;border-top:1px solid var(--border)}}
</style></head><body>
<h1>AlphaX — <span>AI 给你发工资</span></h1>
<p class="subtitle">不做工具。AI 替你打工，月底分钱。</p>
<div class="big-number">
<div class="val">${total:.2f}</div>
<div class="lbl">本月 AI 员工累计赚取</div>
</div>
<div class="grid">{workers_html}</div>
<div class="footer">🚀 {len(status['workers'])} 个 AI 员工在 24h 不间断工作 | 每 5 秒刷新</div>
</body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, *a): pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AlphaX Wage — AI 给人类发工资")
    parser.add_argument("--port", type=int, default=8898)
    args = parser.parse_args()

    print(f"💰 AlphaX Wage")
    print(f"   打开浏览器 → http://localhost:{args.port}")
    print(f"   {len(employer.workers)} 个 AI 员工已就位，开始为你赚钱")

    server = HTTPServer(("0.0.0.0", args.port), WageHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 AI 员工已下班")
        employer._running = False
        server.server_close()
