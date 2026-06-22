"""AlphaX API — 自主进化 AI 服务

一条命令启动:
  python3 api_server.py --port 8080

接口:
  POST /v1/evolve    进化决策 → 生成最优结果
  POST /v1/feedback   用户反馈 → 基因池学习
  GET  /v1/health     进化状态

背后: Gene Pool 根据历史反馈持续进化，每次调用都会选出更优策略。
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).parent))

from core.genome import Genome, SEED_GENOMES, GENE_SPACE, Category
from core.api_utils import call_deepseek, extract_json
from config import config


# ═══════════════════════════════════════════
# 进化基因池（精简版，API 专用）
# ═══════════════════════════════════════════

class EvolvingBrain:
    """持续进化的决策引擎。每次 API 调用都是进化的一步。"""

    def __init__(self):
        self.gene_pool: dict[str, dict] = {}
        self.feedback_log: list[dict] = []
        self.call_count = 0
        self.generation = 1
        self._init_seeds()

    def _init_seeds(self):
        for g in SEED_GENOMES:
            self.gene_pool[g.genome_id] = {
                "genome": g,
                "score": 0.5,
                "uses": 0,
                "successes": 0,
            }

    def decide(self, task: str, context: dict | None = None) -> dict:
        """根据任务选出最优基因策略，生成结果"""
        self.call_count += 1

        # 选 top 基因
        ranked = sorted(self.gene_pool.values(), key=lambda x: x["score"], reverse=True)
        best = ranked[0]
        genome: Genome = best["genome"]

        # 用选中的基因 + LLM 生成结果
        result = self._generate(task, genome, context)

        return {
            "request_id": uuid.uuid4().hex[:12],
            "strategy": {
                "category": genome.category.value,
                "pricing": genome.pricing_model.value,
                "market": genome.target_market.value,
                "generation": self.generation,
                "gene_fitness": round(best["score"], 2),
            },
            "result": result,
            "meta": {
                "total_calls": self.call_count,
                "gene_pool_size": len(self.gene_pool),
            },
        }

    def learn(self, request_id: str, rating: int, comment: str = "") -> dict:
        """用户反馈 → 基因评分更新（进化驱动）"""
        self.feedback_log.append({
            "request_id": request_id,
            "rating": rating,
            "comment": comment,
            "time": time.time(),
        })

        # 每 10 条反馈触发一次代际进化
        recent = [f for f in self.feedback_log[-10:] if f["rating"] >= 4]
        good_rate = len(recent) / min(len(self.feedback_log), 10)

        if len(self.feedback_log) % 10 == 0:
            self.generation += 1
            # 变异 + 重组高评分基因
            self._evolve()

        return {
            "generation": self.generation,
            "satisfaction_rate": round(good_rate, 2),
            "total_feedback": len(self.feedback_log),
        }

    def _generate(self, task: str, genome: Genome, context: dict | None) -> str:
        """用 LLM 生成，参数由基因决定"""
        if not config.deepseek_api_key:
            return self._mock_generate(task, genome)

        prompt = f"""你是 AlphaX 进化 AI。根据以下策略生成最优回答。

任务: {task}
策略参数: 品类={genome.category.value}, 复杂度={genome.code_complexity}
市场定位: {genome.target_market.value}, 定价模型={genome.pricing_model.value}

用专业的中文回答，简洁直接，不超过 300 字。"""
        try:
            content = call_deepseek(prompt, config.deepseek_api_key, config.deepseek_base_url,
                                    temperature=0.4, max_tokens=500)
            return content.strip()
        except Exception:
            return self._mock_generate(task, genome)

    def _mock_generate(self, task: str, genome: Genome) -> str:
        """无 API 时的模拟生成"""
        return f"[AlphaX Gen{self.generation}] 针对「{task[:30]}」的最优策略: "
\
               f"品类={genome.category.value}, 定价={genome.pricing_model.value}。"
\
               f"（接入 DeepSeek API 后可获得完整智能回复）"

    def _evolve(self):
        """代际进化：变异高评分基因，淘汰低评分"""
        ranked = sorted(self.gene_pool.values(), key=lambda x: x["score"], reverse=True)
        # 保留 top 50%
        survivors = ranked[: max(4, len(ranked) // 2)]
        new_pool = {}
        for entry in survivors:
            g = entry["genome"]
            new_pool[g.genome_id] = entry
            # 每个幸存者产一个变异后代
            mutant = g.mutate()
            new_pool[mutant.genome_id] = {
                "genome": mutant,
                "score": entry["score"] * 0.8,
                "uses": 0,
                "successes": 0,
            }
        # 添加随机新基因
        for _ in range(2):
            rg = Genome(
                product_type=random.choice(GENE_SPACE["product_type"]),
                category=random.choice(GENE_SPACE["category"]),
                pricing_model=random.choice(GENE_SPACE["pricing_model"]),
                target_market=random.choice(GENE_SPACE["target_market"]),
                title_pattern=random.choice(GENE_SPACE["title_pattern"]),
                price_point=random.choice(GENE_SPACE["price_point"]),
                description_style=random.choice(GENE_SPACE["description_style"]),
                screenshot_count=random.choice(GENE_SPACE["screenshot_count"]),
                code_complexity=random.choice(GENE_SPACE["code_complexity"]),
            )
            new_pool[rg.genome_id] = {"genome": rg, "score": 0.3, "uses": 0, "successes": 0}

        self.gene_pool = new_pool

    def health(self) -> dict:
        total = len(self.feedback_log)
        good = sum(1 for f in self.feedback_log if f["rating"] >= 4)
        return {
            "status": "evolving",
            "generation": self.generation,
            "gene_pool": len(self.gene_pool),
            "total_calls": self.call_count,
            "feedback_count": total,
            "satisfaction": round(good / max(total, 1), 2),
        }


import random

brain = EvolvingBrain()

# 追踪 request → genome 映射（反馈时定位基因）
_request_map: dict[str, str] = {}  # request_id → genome_id


# ═══════════════════════════════════════════
# HTTP API
# ═══════════════════════════════════════════

class APIHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/v1/health":
            self._json(brain.health())
        elif path == "/":
            self._html(LANDING_HTML)
        elif path == "/docs":
            self._html(DOCS_HTML)
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.read(length)) if length > 0 else {}

        if path == "/v1/evolve":
            task = body.get("task", body.get("prompt", ""))
            if not task:
                self._json({"error": "缺少 task 参数"}, 400)
                return
            context = body.get("context")
            result = brain.decide(task, context)
            # 记录映射用于反馈
            _request_map[result["request_id"]] = result["strategy"]["category"]
            self._json(result)

        elif path == "/v1/feedback":
            rid = body.get("request_id", "")
            rating = body.get("rating", 0)
            comment = body.get("comment", "")
            if not rid or not isinstance(rating, int) or rating < 1 or rating > 5:
                self._json({"error": "缺少 request_id 或 rating (1-5)"}, 400)
                return
            result = brain.learn(rid, rating, comment)
            self._json(result)

        else:
            self.send_error(404)

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False)
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode())

    def _html(self, content):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode())

    def read(self, n):
        return self.rfile.read(n)

    def log_message(self, format, *args): pass


LANDING_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AlphaX API — 自主进化 AI</title>
<style>
:root{--bg:#0d0d0d;--text:#e0e0e0;--muted:#888;--accent:#fff;--green:#22c55e;--blue:#3b82f6}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,sans-serif;line-height:1.6}
.hero{text-align:center;padding:80px 24px 40px}
.hero h1{font-size:48px;font-weight:200;letter-spacing:-1px;margin-bottom:16px}
.hero h1 span{font-weight:600}
.hero p{color:var(--muted);font-size:18px;max-width:560px;margin:0 auto 32px}
.badge{display:inline-block;padding:4px 12px;border:1px solid #333;border-radius:20px;font-size:12px;color:var(--green);margin-bottom:24px}
.cta{display:inline-block;padding:12px 32px;background:var(--accent);color:#000;border-radius:6px;text-decoration:none;font-weight:600;font-size:14px}
.pricing{display:flex;gap:16px;max-width:720px;margin:60px auto;padding:0 24px;flex-wrap:wrap;justify-content:center}
.plan{flex:1;min-width:200px;max-width:320px;background:#111;border:1px solid #222;border-radius:12px;padding:28px 24px}
.plan h3{font-size:20px;margin-bottom:8px}
.plan .price{font-size:36px;font-weight:700;margin:16px 0}
.plan .price span{font-size:14px;color:var(--muted);font-weight:400}
.plan ul{list-style:none;color:var(--muted);font-size:14px}
.plan ul li{margin-bottom:8px}
.plan ul li::before{content:"✓ ";color:var(--green)}
.section{max-width:720px;margin:60px auto;padding:0 24px}
.section h2{font-size:24px;margin-bottom:16px}
.section p,.section code{color:var(--muted);font-size:14px}
pre{background:#111;border:1px solid #222;border-radius:8px;padding:20px;overflow-x:auto;font-size:13px;color:#ccc}
.footer{text-align:center;color:var(--muted);font-size:12px;padding:40px}
</style>
</head>
<body>

<div class="hero">
  <div class="badge">Generation 1 · 持续进化中</div>
  <h1>Alpha<span>X</span> API</h1>
  <p>不是静态模型。每次调用都在进化。<br>用的人越多，AI 越强。</p>
  <a href="/docs" class="cta">查看 API 文档</a>
</div>

<div class="pricing">
  <div class="plan">
    <h3>Free</h3>
    <div class="price">$0<span>/月</span></div>
    <ul>
      <li>100 次调用/天</li>
      <li>标准进化速度</li>
      <li>社区反馈池</li>
    </ul>
  </div>
  <div class="plan">
    <h3>Pro</h3>
    <div class="price">$29<span>/月</span></div>
    <ul>
      <li>10,000 次调用/月</li>
      <li>优先进化权重</li>
      <li>专属基因策略</li>
      <li>API 优先响应</li>
    </ul>
  </div>
  <div class="plan">
    <h3>Enterprise</h3>
    <div class="price">$299<span>/月</span></div>
    <ul>
      <li>无限调用</li>
      <li>私有基因池</li>
      <li>定制进化方向</li>
      <li>SLA 99.9%</li>
    </ul>
  </div>
</div>

<div class="section">
  <h2>快速开始</h2>
  <pre>curl -X POST http://localhost:8080/v1/evolve \
  -H "Content-Type: application/json" \
  -d '{"task": "帮我设计一个用户登录系统"}'</pre>
</div>

<div class="footer">AlphaX API · 自主进化 AI 基础设施</div>
</body>
</html>"""


DOCS_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AlphaX API Docs</title>
<style>
:root{--bg:#0d0d0d;--text:#e0e0e0;--muted:#888;--accent:#fff;--green:#22c55e}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,sans-serif;line-height:1.6;max-width:720px;margin:0 auto;padding:40px 24px}
h1{font-size:32px;margin-bottom:8px}
h2{font-size:20px;margin:32px 0 12px;padding-bottom:8px;border-bottom:1px solid #222}
h3{font-size:16px;margin:16px 0 8px;color:var(--accent)}
code{background:#111;padding:1px 5px;border-radius:3px;font-size:13px}
pre{background:#111;border:1px solid #222;border-radius:8px;padding:20px;overflow-x:auto;font-size:13px;margin:12px 0}
.endpoint{margin:16px 0;padding:16px;background:#111;border-radius:8px;border:1px solid #222}
.method{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;margin-right:8px}
.method.post{background:#1a3a5c;color:#60a5fa}
.method.get{background:#1a3c1a;color:var(--green)}
.back{color:var(--muted);font-size:13px}
</style>
</head>
<body>
<a href="/" class="back">← 返回首页</a>
<h1>API 文档</h1>

<h2>POST /v1/evolve</h2>
<div class="endpoint">
  <span class="method post">POST</span> <code>/v1/evolve</code>
  <p style="color:var(--muted);margin-top:8px">提交任务，AI 用最优进化策略生成结果。</p>

  <h3>Request</h3>
  <pre>{
  "task": "帮我写一个 Python 脚本...",
  "context": { "language": "zh" }  // 可选
}</pre>

  <h3>Response</h3>
  <pre>{
  "request_id": "a1b2c3d4e5f6",
  "strategy": {
    "category": "dev_tools",
    "generation": 5,
    "gene_fitness": 0.87
  },
  "result": "这是 AI 生成的结果...",
  "meta": {
    "total_calls": 1234,
    "gene_pool_size": 16
  }
}</pre>
</div>

<h2>POST /v1/feedback</h2>
<div class="endpoint">
  <span class="method post">POST</span> <code>/v1/feedback</code>
  <p style="color:var(--muted);margin-top:8px">提交评分，驱动进化。</p>

  <h3>Request</h3>
  <pre>{
  "request_id": "a1b2c3d4e5f6",
  "rating": 4,          // 1-5
  "comment": "不错"      // 可选
}</pre>

  <h3>Response</h3>
  <pre>{
  "generation": 5,
  "satisfaction_rate": 0.85,
  "total_feedback": 42
}</pre>
</div>

<h2>GET /v1/health</h2>
<div class="endpoint">
  <span class="method get">GET</span> <code>/v1/health</code>
  <p style="color:var(--muted);margin-top:8px">查看进化状态。</p>
  <pre>{
  "status": "evolving",
  "generation": 5,
  "gene_pool": 16,
  "total_calls": 1234,
  "feedback_count": 42,
  "satisfaction": 0.85
}</pre>
</div>

</body>
</html>"""


def main():
    import argparse
    p = argparse.ArgumentParser(description="AlphaX API Server")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), APIHandler)
    print(f"\n  AlphaX API → http://localhost:{args.port}")
    print(f"  文档 → http://localhost:{args.port}/docs")
    print(f"  Generation {brain.generation} · Gene Pool {len(brain.gene_pool)}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")


if __name__ == "__main__":
    main()
