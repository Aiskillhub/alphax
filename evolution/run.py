"""AlphaX 统一入口 — 进化引擎 + 产品构建 + 商店 + 仪表盘

一条命令启动全部:
  python3 -m evolution.run --port 8080

打开浏览器看到:
  /          进化仪表盘（种群、基因池）
  /store     产品销售商店（顾客入口）
  /demo/{id} 产品在线体验
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from evolution.engine import EvolutionEngine
from evolution.environment import SimulatedEnvironment
from evolution.dashboard import EvolutionDashboard, HTML as DASH_HTML
from builder.web_tool_builder import WebToolBuilder
from config import config

STORE_DIR = config.data_dir / "store"
STORE_DIR.mkdir(exist_ok=True)
PRODUCTS_FILE = STORE_DIR / "products.json"
BUILDS_DIR = config.data_dir / "builds"
BUILDS_DIR.mkdir(exist_ok=True)


class LiveStore:
    """轻量商店：产品注册 + 展示 + demo"""

    def __init__(self):
        self.products: dict[str, dict] = {}
        self._load()

    def _load(self):
        if PRODUCTS_FILE.exists():
            try:
                self.products = json.loads(PRODUCTS_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self):
        PRODUCTS_FILE.write_text(json.dumps(self.products, indent=2, ensure_ascii=False))

    def publish(self, genome, build_dir: str) -> str:
        """注册一个产品到商店"""
        pid = genome.genome_id[:12]
        self.products[pid] = {
            "id": pid,
            "name": genome.express(),
            "category": genome.category.value,
            "price": genome.price_point,
            "pricing": genome.pricing_model.value,
            "market": genome.target_market.value,
            "complexity": genome.code_complexity,
            "fitness": round(genome.fitness_score, 2),
            "build_dir": build_dir,
            "published_at": time.strftime("%Y-%m-%d %H:%M"),
        }
        self._save()
        return pid

    def list_products(self) -> list[dict]:
        return sorted(self.products.values(),
                      key=lambda p: p.get("fitness", 0), reverse=True)

    def get_demo_html(self, pid: str) -> str | None:
        """读取产品的 index.html 作为 demo"""
        product = self.products.get(pid)
        if not product:
            return None
        build_dir = product.get("build_dir", "")
        html_path = Path(build_dir) / "index.html" if build_dir else None
        if html_path and html_path.exists():
            return html_path.read_text()
        return None


def build_from_genome(genome, organism_id: str = "") -> str:
    """用 WebToolBuilder 构建真实产品，返回 build_dir 路径"""
    builder = WebToolBuilder()
    oid = organism_id or genome.genome_id[:12]
    try:
        result = builder.build(genome, oid)
        return str(result)
    except Exception:
        return str(BUILDS_DIR / f"webtool_{oid}")


class UnifiedHandler(BaseHTTPRequestHandler):
    """统一 HTTP 服务：仪表盘 + 商店 + API"""

    dashboard: EvolutionDashboard = None
    store: LiveStore = None

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self._serve_dashboard()
        elif path == "/store":
            self._serve_store()
        elif path.startswith("/demo/"):
            self._serve_demo(path.split("/demo/")[1])
        elif path == "/api/state":
            self._json(self.dashboard.state())  # pyright: ignore[reportOptionalMemberAccess]
        elif path == "/api/products":
            self._json(self.store.list_products())  # pyright: ignore[reportOptionalMemberAccess]
        elif path == "/api/build":
            self._trigger_build()
        else:
            self.send_error(404)

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False, default=str)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode())

    def _serve_dashboard(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(DASH_HTML.encode())

    def _serve_store(self):
        products = self.store.list_products()  # pyright: ignore[reportOptionalMemberAccess]
        # 过滤掉旧格式产品
        products = [p for p in products if p.get('category')]
        cards = ""
        for p in products[-30:]:  # 最近30个
            cat = p.get('category', '')
            cards += f"""<div class="card">
  <div class="icon">{_icon(cat)}</div>
  <div class="info">
    <div class="name">{p['name']}</div>
    <div class="meta">{cat} · {p.get('pricing','')} · {p.get('market','')}</div>
    <div class="meta">适应度: {p.get('fitness', 0)} · 复杂度: {p.get('complexity','')}</div>
  </div>
  <div class="price">${p.get('price', 0):.2f}</div>
  <a class="btn" href="/demo/{p['id']}" target="_blank">试用</a>
</div>"""
        html = STORE_HTML.replace("{{CARDS}}", cards or '<div class="empty">进化引擎运行中，产品将自动上架...</div>')
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def _serve_demo(self, pid: str):
        html = self.store.get_demo_html(pid)  # pyright: ignore[reportOptionalMemberAccess]
        if not html:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def _trigger_build(self):
        """手动触发一次构建+上架"""
        genome = self.dashboard.engine.gene_pool._random_genome()  # pyright: ignore[reportOptionalMemberAccess]
        build_dir = build_from_genome(genome)
        pid = self.store.publish(genome, build_dir)  # pyright: ignore[reportOptionalMemberAccess]
        self._json({"status": "ok", "product_id": pid, "name": genome.express()})

    def log_message(self, format, *args): pass


def _icon(cat: str) -> str:
    return {"ai_chat": "💬", "dev_tools": "🔧", "productivity": "📋",
            "automation": "⚡", "content": "📝", "data": "📊", "seo": "🔍"}.get(cat, "📦")


class EvolutionRunner:
    """协调引擎 + 产品构建 + 商店上架"""

    def __init__(self, days: int = 0, seed: int = 42):
        config.survival_threshold_days = 3
        config.initial_capital = 200.0
        self.dash = EvolutionDashboard(days=days, seed=seed)
        self.dash.engine.chamber.fund.pool_balance = 200.0
        self.dash.engine.chamber.fund.transactions.clear()
        self.dash.engine.chamber.fund.total_hatch_costs = 0.0
        self.store = LiveStore()

    def run(self):
        self.dash.start()
        # 启动产品构建线程
        t = threading.Thread(target=self._build_loop, daemon=True)
        t.start()

    def _build_loop(self):
        """定期将新 organism 构建成真实产品并上架"""
        built_ids = set()
        while self.dash.running:
            time.sleep(5)
            try:
                active = self.dash.engine.chamber.hive.active_organisms
                for org in active:
                    if not org.genome or org.organism_id in built_ids:
                        continue
                    if org.days_alive < 2:
                        continue  # 等它稳定一下
                    built_ids.add(org.organism_id)
                    genome = org.genome
                    build_dir = build_from_genome(genome, org.organism_id)
                    self.store.publish(genome, build_dir)
            except Exception:
                pass


STORE_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AlphaX Store — 自主进化产品</title>
<style>
:root{--bg:#0f1117;--card:#1a1d27;--border:#2a2d3a;--text:#e2e8f0;--muted:#8890a4;--green:#22c55e;--blue:#3b82f6;--red:#ef4444}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:900px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;margin-bottom:4px}
h1 span{color:var(--blue)}
.sub{color:var(--muted);font-size:13px;margin-bottom:24px}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:10px;display:flex;align-items:center;gap:14px}
.card:hover{border-color:var(--blue)}
.card .icon{font-size:28px;min-width:36px;text-align:center}
.card .info{flex:1;min-width:0}
.card .name{font-weight:600;font-size:15px}
.card .meta{color:var(--muted);font-size:11px;margin-top:3px}
.card .price{font-weight:700;font-size:18px;color:var(--green);min-width:70px;text-align:right}
.btn{display:inline-block;padding:8px 16px;background:var(--blue);color:#fff;border-radius:6px;text-decoration:none;font-size:12px;font-weight:500}
.btn:hover{opacity:.9}
.empty{text-align:center;padding:60px 20px;color:var(--muted);font-size:14px}
.footer{text-align:center;color:var(--muted);font-size:11px;margin-top:30px}
</style>
</head>
<body>
<h1>Alpha<span>X</span> Store</h1>
<div class="sub">AI 自主进化的数字产品，每 5 分钟上架新品</div>
{{CARDS}}
<div class="footer">AlphaX Evolution Runtime · 产品由 AI 自动生成并进化</div>
</body>
</html>"""


def main():
    import argparse
    p = argparse.ArgumentParser(description="AlphaX Unified Runtime")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--days", type=int, default=0, help="0=无限")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    runner = EvolutionRunner(days=args.days, seed=args.seed)
    runner.run()

    UnifiedHandler.dashboard = runner.dash
    UnifiedHandler.store = runner.store

    server = HTTPServer(("0.0.0.0", args.port), UnifiedHandler)
    print(f"""
  ╔══════════════════════════════════════════╗
  ║       AlphaX Evolution Runtime           ║
  ╠══════════════════════════════════════════╣
  ║  仪表盘   → http://localhost:{args.port}        ║
  ║  商店     → http://localhost:{args.port}/store   ║
  ║  产品Demo → http://localhost:{args.port}/demo/{id}║
  ╚══════════════════════════════════════════╝
  进化引擎已启动，产品自动构建并上架...
  """)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")
        runner.dash.running = False


if __name__ == "__main__":
    main()
