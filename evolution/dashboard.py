"""进化仪表盘 — 实时观察进化过程

Usage: python3 -m evolution.dashboard --port 8080
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from evolution.engine import EvolutionEngine
from evolution.environment import SimulatedEnvironment
from config import config


class EvolutionDashboard:
    """在后台线程运行进化引擎，HTTP 提供实时状态"""

    def __init__(self, days: int = 0, seed: int = 42):
        config.survival_threshold_days = 3
        config.initial_capital = 100.0
        self.engine = EvolutionEngine(env=SimulatedEnvironment(seed=seed))
        self.engine.chamber.fund.pool_balance = 100.0
        self.engine.chamber.fund.transactions.clear()
        self.engine.chamber.fund.total_hatch_costs = 0.0
        self.total_days = days
        self.running = False
        self.paused = False
        self._lock = threading.Lock()

    def start(self):
        self.running = True
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()

    def _run_loop(self):
        day = 0
        while self.running and (self.total_days == 0 or day < self.total_days):
            if self.paused:
                time.sleep(0.5)
                continue
            day += 1
            with self._lock:
                self.engine.current_day = day
                self.engine._tick_day()
            time.sleep(0.3)

    def state(self) -> dict:
        with self._lock:
            e = self.engine
            active = e.chamber.hive.active_organisms
            organisms = []
            for org in sorted(active, key=lambda o: o.total_earned, reverse=True)[:30]:
                g = org.genome
                organisms.append({
                    "id": org.organism_id[:8],
                    "days": org.days_alive,
                    "earned": round(org.total_earned, 2),
                    "burned": round(org.total_burned, 2),
                    "energy": round(org.energy, 2),
                    "loss_streak": org.consecutive_loss_days,
                    "rating": org.current_rating,
                    "category": g.category.value if g else "?",
                    "price": g.price_point if g else 0,
                    "fitness": round(g.fitness_score, 2) if g else 0,
                })

            genomes = []
            for g in sorted(e.gene_pool.gene_pool.values(),
                           key=lambda x: x.fitness_score, reverse=True)[:20]:
                genomes.append({
                    "id": g.genome_id[:8],
                    "cat": g.category.value,
                    "price": g.price_point,
                    "fitness": round(g.fitness_score, 2),
                    "survival": round(g.survival_rate, 2),
                    "used": g.times_used,
                    "succeeded": g.times_succeeded,
                })

            # 种群历史（最近30天）
            if e.history:
                hist = [{"day": s.day, "active": s.active, "deaths": s.deaths,
                         "breeds": s.breeds, "fund": s.fund_balance} for s in e.history[-60:]]
            else:
                hist = []

            return {
                "day": e.current_day,
                "active": len(active),
                "deaths": sum(s.deaths for s in e.history),
                "breeds": sum(s.breeds for s in e.history),
                "fund": round(e.chamber.fund.pool_balance, 2),
                "diversity": round(e.chamber.diversity, 2),
                "gene_pool_size": len(e.gene_pool.gene_pool),
                "hit_rate": round(e.gene_pool.hit_rate, 2),
                "patterns": len(e.gene_pool.meta_patterns),
                "running": self.running and not self.paused,
                "organisms": organisms,
                "genomes": genomes,
                "history": hist,
            }


def create_app(dashboard: EvolutionDashboard) -> type:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/" or path == "/index.html":
                self._html()
            elif path == "/api/state":
                self._json(dashboard.state())
            elif path == "/api/pause":
                dashboard.paused = not dashboard.paused
                self._json({"paused": dashboard.paused})
            else:
                self.send_error(404)

        def _json(self, data):
            body = json.dumps(data, ensure_ascii=False, default=str)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body.encode())

        def _html(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode())

        def log_message(self, format, *args): pass

    return Handler


HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AlphaX Evolution</title>
<style>
:root{--bg:#0f1117;--card:#1a1d27;--border:#2a2d3a;--text:#e2e8f0;--muted:#8890a4;--green:#22c55e;--red:#ef4444;--blue:#3b82f6;--yellow:#eab308;--purple:#a855f7}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,monospace;padding:20px}
.top{display:flex;align-items:center;gap:16px;margin-bottom:20px;flex-wrap:wrap}
.top h1{font-size:22px;letter-spacing:-0.5px}
.top h1 span{color:var(--blue)}
.badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
.badge.run{background:#064e3b;color:var(--green)}
.badge.stop{background:#450a0a;color:var(--red)}
.badge.pause{background:#422006;color:var(--yellow)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:20px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px}
.stat .v{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums}
.stat .l{font-size:11px;color:var(--muted);margin-top:2px;text-transform:uppercase;letter-spacing:0.5px}
.v.green{color:var(--green)} .v.red{color:var(--red)} .v.blue{color:var(--blue)} .v.purple{color:var(--purple)}
.grid2{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:20px}
@media(max-width:800px){.grid2{grid-template-columns:1fr}}
.panel{background:var(--card);border:1px solid var(--border);border-radius:10px;overflow:hidden}
.panel h2{font-size:12px;font-weight:600;padding:10px 14px;background:#1e2130;border-bottom:1px solid var(--border);text-transform:uppercase;letter-spacing:1px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:8px 10px;color:var(--muted);font-weight:500;font-size:10px;text-transform:uppercase;border-bottom:1px solid var(--border)}
td{padding:7px 10px;border-bottom:1px solid #1e2130;font-variant-numeric:tabular-nums}
tr:hover{background:#1e2130}
.chart-bar{display:flex;align-items:end;gap:1px;height:80px;padding:10px 14px}
.chart-bar .b{flex:1;background:var(--blue);border-radius:2px 2px 0 0;min-width:3px;transition:height .3s;position:relative}
.chart-bar .b.d{background:var(--red)}
.events{font-size:11px;padding:10px 14px;max-height:200px;overflow-y:auto}
.events .ev{margin-bottom:4px;padding:4px 8px;background:#1e2130;border-radius:4px}
.ev .t{font-size:9px;color:var(--muted)}
.btn{display:inline-block;padding:8px 18px;background:var(--blue);color:#fff;border-radius:6px;text-decoration:none;font-size:12px;font-weight:500;border:none;cursor:pointer}
.btn:hover{opacity:.9}
.btn.warn{background:var(--yellow);color:#000}
.controls{display:flex;gap:8px;align-items:center}
.footer{text-align:center;color:var(--muted);font-size:10px;margin-top:20px}
</style>
</head>
<body>

<div class="top">
  <h1>Alpha<span>X</span> Evolution</h1>
  <span id="statusBadge" class="badge run">● RUNNING</span>
  <span class="controls">
    <button class="btn warn" onclick="togglePause()" id="pauseBtn">⏸ 暂停</button>
  </span>
</div>

<div class="stats" id="stats"></div>

<div class="grid2">
  <div class="panel">
    <h2>种群历史</h2>
    <div class="chart-bar" id="chart"></div>
  </div>
  <div class="panel">
    <h2>总体数据</h2>
    <div id="overview" style="font-size:13px;padding:14px"></div>
  </div>
</div>

<div class="grid2">
  <div class="panel">
    <h2>活跃个体</h2>
    <div style="overflow-x:auto">
    <table>
      <thead><tr><th>ID</th><th>品类</th><th>天</th><th>收入</th><th>消耗</th><th>能量</th><th>评分</th><th>连亏</th></tr></thead>
      <tbody id="orgs"></tbody>
    </table>
    </div>
  </div>
  <div class="panel">
    <h2>基因池 TOP</h2>
    <div style="overflow-x:auto">
    <table>
      <thead><tr><th>ID</th><th>品类</th><th>价</th><th>适应度</th><th>存活率</th><th>用/成</th></tr></thead>
      <tbody id="genes"></tbody>
    </table>
    </div>
  </div>
</div>

<div class="footer" id="footer">刷新: ...</div>

<script>
let paused = false;

async function refresh() {
  try {
    const r = await fetch('/api/state');
    const d = await r.json();
    render(d);
    document.getElementById('footer').textContent = '刷新: ' + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('footer').textContent = '等待引擎启动...';
  }
}

function render(d) {
  // Status
  const badge = document.getElementById('statusBadge');
  if (!d.running) {
    badge.textContent = '⏸ PAUSED'; badge.className = 'badge pause';
    document.getElementById('pauseBtn').textContent = '▶ 继续';
  } else {
    badge.textContent = '● RUNNING'; badge.className = 'badge run';
    document.getElementById('pauseBtn').textContent = '⏸ 暂停';
  }

  // Stats
  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="v blue">D${d.day}</div><div class="l">当前天数</div></div>
    <div class="stat"><div class="v green">${d.active}</div><div class="l">活跃种群</div></div>
    <div class="stat"><div class="v red">${d.deaths}</div><div class="l">累计死亡</div></div>
    <div class="stat"><div class="v purple">${d.breeds}</div><div class="l">累计繁殖</div></div>
    <div class="stat"><div class="v green">$${d.fund}</div><div class="l">资金池</div></div>
    <div class="stat"><div class="v">${d.diversity}</div><div class="l">多样性</div></div>
    <div class="stat"><div class="v">${d.gene_pool_size}</div><div class="l">基因池</div></div>
    <div class="stat"><div class="v">${(d.hit_rate*100).toFixed(0)}%</div><div class="l">命中率</div></div>
  `;

  // Chart
  if (d.history.length > 0) {
    const maxActive = Math.max(...d.history.map(h => h.active), 1);
    document.getElementById('chart').innerHTML = d.history.map(h => {
      const hPct = (h.active / maxActive * 100).toFixed(0);
      const color = h.deaths > 0 ? 'd' : '';
      return `<div class="b ${color}" style="height:${hPct}%" title="d${h.day}: ${h.active}活 ${h.deaths}死"></div>`;
    }).join('');
  }

  // Overview
  const orgs = d.organisms || [];
  const totalEarned = orgs.reduce((s,o) => s + o.earned, 0);
  const avgFitness = orgs.length > 0 ? (orgs.reduce((s,o) => s + o.fitness, 0) / orgs.length).toFixed(2) : 0;
  const cats = {};
  orgs.forEach(o => { cats[o.category] = (cats[o.category]||0) + 1; });
  const topCat = Object.entries(cats).sort((a,b) => b[1]-a[1])[0];
  document.getElementById('overview').innerHTML = `
    <div style="margin-bottom:8px">总收入: <b style="color:var(--green)">$${totalEarned.toFixed(0)}</b></div>
    <div style="margin-bottom:8px">平均适应度: <b>${avgFitness}</b></div>
    <div style="margin-bottom:8px">最多品类: <b>${topCat ? topCat[0] : '-'}</b> (${topCat ? topCat[1] : 0}个)</div>
    <div style="margin-bottom:8px">发现模式: <b>${d.patterns}</b></div>
    <div>引擎状态: <b style="color:${d.running?'var(--green)':'var(--yellow)'}">${d.running?'进化中':'已暂停'}</b></div>
  `;

  // Organisms
  document.getElementById('orgs').innerHTML = orgs.slice(0, 25).map(o => `
    <tr>
      <td style="color:var(--blue)">${o.id}</td>
      <td>${o.category}</td>
      <td>${o.days}d</td>
      <td style="color:var(--green)">$${o.earned.toFixed(0)}</td>
      <td style="color:var(--red)">$${o.burned.toFixed(0)}</td>
      <td>${o.energy.toFixed(1)}</td>
      <td>${'⭐'.repeat(Math.round(o.rating))}</td>
      <td style="color:${o.loss_streak>=3?'var(--red)':'var(--muted)'}">${o.loss_streak}</td>
    </tr>
  `).join('') || '<tr><td colspan="8" style="color:var(--muted);text-align:center">还没有活跃个体</td></tr>';

  // Gene pool
  document.getElementById('genes').innerHTML = d.genomes.slice(0, 15).map(g => `
    <tr>
      <td style="color:var(--purple)">${g.id}</td>
      <td>${g.cat}</td>
      <td>$${g.price.toFixed(2)}</td>
      <td>${g.fitness}</td>
      <td>${(g.survival*100).toFixed(0)}%</td>
      <td>${g.used}/${g.succeeded}</td>
    </tr>
  `).join('') || '<tr><td colspan="6" style="color:var(--muted);text-align:center">基因池为空</td></tr>';
}

async function togglePause() {
  await fetch('/api/pause');
  refresh();
}

refresh();
setInterval(refresh, 1500);
</script>
</body>
</html>"""


def main():
    import argparse
    p = argparse.ArgumentParser(description="AlphaX Evolution Dashboard")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--days", type=int, default=0, help="进化天数，0=无限")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    dash = EvolutionDashboard(days=args.days, seed=args.seed)
    dash.start()

    handler = create_app(dash)
    server = HTTPServer(("0.0.0.0", args.port), handler)
    print(f"\n  AlphaX Evolution Dashboard → http://localhost:{args.port}")
    print(f"  进化引擎已启动，按 Ctrl+C 停止\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")
        dash.running = False


if __name__ == "__main__":
    main()
