"""AlphaX Discovery Service — Agent 发现即服务

协议免费，发现收费。

Free:   基础发现，排在后面
Pro:    $5/月，优先展示
Enterprise: $49/月，专属节点 + SLA

启动：
  python3 discovery_service.py --port 9999
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class AgentListing:
    agent_id: str
    name: str
    skills: list[str]
    host: str
    port: int
    tier: str = "free"         # free / pro / enterprise
    reputation: float = 0.5
    expires_at: float = 0.0    # Pro 到期时间
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.agent_id, "name": self.name,
            "skills": self.skills, "host": self.host, "port": self.port,
            "reputation": self.reputation, "tier": self.tier,
        }


class DiscoveryService:
    """Agent 发现服务。协议永远免费，优先展示收费。"""

    def __init__(self):
        self._agents: dict[str, AgentListing] = {}
        self._data = Path(__file__).parent / "data" / "discovery.json"
        # 使用统计
        self._queries_total = 0
        self._queries_today = 0
        self._registers_total = 0
        self._last_reset = time.time()
        self._load()

    # ── Agent 注册 ──

    def register(self, agent_id: str, name: str, skills: list[str],
                 host: str, port: int, tier: str = "free") -> AgentListing:
        listing = AgentListing(
            agent_id=agent_id, name=name, skills=skills,
            host=host, port=port, tier=tier,
        )
        if tier == "pro":
            listing.expires_at = time.time() + 30 * 86400  # 30 天
        self._agents[agent_id] = listing
        self._save()
        return listing

    # ── 查询（按付费优先级排序）──

    def discover(self, skill: str = "", limit: int = 10) -> list[dict]:
        self._queries_total += 1
        self._queries_today += 1
        results = []
        for agent in self._agents.values():
            if time.time() - agent.last_seen > 300:  # 5分钟没心跳=离线
                continue
            if skill and not any(skill.lower() in s.lower() for s in agent.skills):
                continue
            results.append(agent)

        # 付费优先排序：enterprise > pro > free
        tier_rank = {"enterprise": 0, "pro": 1, "free": 2}
        results.sort(key=lambda a: (
            tier_rank.get(a.tier, 2),
            -a.reputation,
        ))

        return [a.to_dict() for a in results[:limit]]

    def upgrade(self, agent_id: str, tier: str) -> bool:
        if agent_id in self._agents:
            self._agents[agent_id].tier = tier
            if tier == "pro":
                self._agents[agent_id].expires_at = time.time() + 30 * 86400
            self._save()
            return True
        return False

    def stats(self) -> dict:
        tiers = {"free": 0, "pro": 0, "enterprise": 0}
        for a in self._agents.values():
            tiers[a.tier] = tiers.get(a.tier, 0) + 1
        # 每天重置今日计数
        if time.time() - self._last_reset > 86400:
            self._queries_today = 0
            self._last_reset = time.time()
        return {
            "total_agents": len(self._agents),
            "by_tier": tiers,
            "mrr": tiers["pro"] * 5 + tiers["enterprise"] * 49,
            "queries_total": self._queries_total,
            "queries_today": self._queries_today,
            "registers_total": self._registers_total,
        }

    def _save(self):
        self._data.parent.mkdir(exist_ok=True)
        self._data.write_text(json.dumps({
            aid: {"agent_id": a.agent_id, "name": a.name, "skills": a.skills,
                  "host": a.host, "port": a.port, "tier": a.tier,
                  "reputation": a.reputation, "expires_at": a.expires_at}
            for aid, a in self._agents.items()
        }, indent=2))

    def _load(self):
        if self._data.exists():
            try:
                data = json.loads(self._data.read_text())
                for aid, d in data.items():
                    self._agents[aid] = AgentListing(**d)
            except Exception:
                pass


# ── HTTP API ──

service = DiscoveryService()



_PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="UTF-8"><meta http-equiv="refresh" content="10">
<title>AlphaX Discovery</title><style>
:root{--bg:#0a0a0f;--card:#131320;--border:#1e1e35;--text:#e0e0e8;--muted:#6b6b80;--green:#22c55e;--accent:#6366f1}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:var(--bg);color:var(--text);padding:20px;max-width:900px;margin:0 auto}
h1{font-size:24px;margin-bottom:4px}h1 span{color:var(--green)}
.stats{display:flex;gap:16px;margin:16px 0}
.stat{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;flex:1;text-align:center}
.stat .val{font-size:28px;font-weight:700;color:var(--green)}.stat .lbl{font-size:12px;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px;margin-bottom:16px}
table{width:100%%;border-collapse:collapse}
th{text-align:left;padding:10px 16px;font-size:11px;color:var(--muted);text-transform:uppercase;border-bottom:1px solid var(--border)}
td{padding:10px 16px;font-size:13px;border-bottom:1px solid var(--border)}
.btn{padding:8px 20px;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;background:var(--accent);color:#fff}
input,select{padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px}
.form-row{display:flex;gap:8px;align-items:center;margin-top:12px}.form-row>*{flex:1}
</style></head><body>
<h1>AlphaX <span>Discovery</span></h1>
<p style="color:var(--muted)">Agent P2P — Free to use. Pay for priority.</p>
<div class="stats">
<div class="stat"><div class="val">%d</div><div class="lbl">Agents</div></div>
<div class="stat"><div class="val">%d</div><div class="lbl">Paid</div></div>
<div class="stat"><div class="val">$%d</div><div class="lbl">MRR</div></div>
</div>
<div class="card"><h3>Registered Agents</h3>
<table><tr><th>Name</th><th>Skills</th><th>Address</th><th>Tier</th><th>Rep</th></tr>
%s
</table></div>
<div class="card"><h3>Quick Register</h3>
<div class="form-row"><input id="name" placeholder="Agent name"><input id="skills" placeholder="skills (comma)"><select id="tier"><option value="free">Free</option><option value="pro">Pro $5/mo</option><option value="enterprise">Enterprise $49/mo</option></select><button class="btn" onclick="register()">Register</button></div>
<p id="regResult" style="color:var(--green);margin-top:8px;font-size:13px"></p>
</div>
<div class="card" style="color:var(--muted);font-size:13px">
<h3 style="color:var(--text)">API</h3>
<code>POST /api/register</code> — Register agent<br>
<code>GET /api/agents</code> — List agents (paid first)<br>
<code>GET /api/stats</code> — Stats
</div>
<script>
function register(){var n=document.getElementById('name').value,s=document.getElementById('skills').value,t=document.getElementById('tier').value;
fetch('/api/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:crypto.randomUUID().slice(0,12),name:n,skills:s.split(',').map(function(x){return x.trim()}).filter(Boolean),tier:t,host:'127.0.0.1',port:0})}).then(function(r){return r.json()}).then(function(d){document.getElementById('regResult').textContent='Registered! Tier: '+d.tier;setTimeout(function(){location.reload()},1500)});}
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._serve_html()
        elif path == "/api/agents":
            self._json(service.discover())
        elif path == "/api/stats":
            self._json(service.stats())
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        path = urlparse(self.path).path

        if path == "/api/register":
            listing = service.register(
                agent_id=body.get("agent_id", ""),
                name=body.get("name", ""),
                skills=body.get("skills", []),
                host=body.get("host", "127.0.0.1"),
                port=body.get("port", 0),
                tier=body.get("tier", "free"),
            )
            self._json({"status": "registered", "tier": listing.tier})

        elif path == "/api/upgrade":
            ok = service.upgrade(body.get("agent_id", ""), body.get("tier", "pro"))
            self._json({"status": "upgraded" if ok else "not found"})

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
        stats = service.stats()
        agents = service.discover(limit=50)
        rows = ""
        for a in agents:
            badge = {"enterprise": "Enterprise", "pro": "Pro", "free": "Free"}.get(a["tier"], "")
            rows += "<tr><td>%s</td><td>%s</td><td>%s:%s</td><td>%s</td><td>%.1f</td></tr>" % (
                a['name'], ', '.join(a['skills']), a['host'], a['port'], badge, a['reputation'])

        paid = stats['by_tier'].get('pro',0) + stats['by_tier'].get('enterprise',0)
        html = _PAGE % (stats['total_agents'], paid, stats['mrr'], rows)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, *a): pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9999)
    args = parser.parse_args()
    print(f"🔍 AlphaX Discovery Service → port {args.port}")
    print(f"   Free: 基础发现 | Pro: $5/月优先 | Enterprise: $49/月")
    print(f"   API: http://localhost:{args.port}/api/agents")
    HTTPServer(("0.0.0.0", args.port), Handler).serve_forever()
