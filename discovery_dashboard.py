"""Discovery Node Dashboard — web UI for the A2A Bridge."""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

from discovery_node import DiscoveryNode

node = DiscoveryNode(port=9999)

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AlphaX Discovery Node</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0f172a;color:#e2e8f0;line-height:1.6}
.container{max-width:900px;margin:0 auto;padding:24px}
.hero{text-align:center;padding:48px 24px;background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #334155;border-radius:16px;margin-bottom:24px}
.hero h1{font-size:2rem}.gradient{background:linear-gradient(135deg,#a78bfa,#3b82f6);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:24px}
.stat{background:#1e293b;padding:20px;border-radius:12px;text-align:center;border:1px solid #334155}
.stat .value{font-size:2rem;font-weight:700;color:#3b82f6}.stat .label{color:#94a3b8;font-size:.85rem;margin-top:4px}
.panel{background:#1e293b;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #334155}
.panel h2{font-size:1.2rem;margin-bottom:16px;color:#f8fafc}
table{width:100%;border-collapse:collapse}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #334155;font-size:.9rem}
th{color:#94a3b8}tr:hover{background:rgba(59,130,246,.05)}
code{background:#1e293b;padding:2px 8px;border-radius:4px;color:#a78bfa}
pre{background:#0f172a;padding:16px;border-radius:8px;overflow-x:auto;font-size:.85rem}
footer{text-align:center;padding:40px;color:#475569}
.badge{display:inline-block;width:8px;height:8px;border-radius:50%;background:#3fb950;margin-right:6px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
</style>
</head>
<body>
<div class="container">
<div class="hero">
<h1><span class="gradient">AlphaX</span> Discovery Node</h1>
<p style="color:#94a3b8;margin-top:8px">Agent-to-Agent Bridge Protocol</p>
</div>
<div class="stats" id="stats"></div>
<div class="panel">
<h2><span class="badge"></span> Online Agents</h2>
<table><thead><tr><th>Agent</th><th>Skills</th><th>Reputation</th></tr></thead><tbody id="agents"></tbody></table>
</div>
<div class="panel">
<h2>Connect Your Agent</h2>
<pre>from alphax import Bridge

agent = Bridge("My Agent", skills=["code-review"],
               discovery_nodes=["DISCOVERY_URL"])
agent.start()</pre>
</div>
<footer>AlphaX Discovery Node — Agent-to-Agent Bridge Protocol</footer>
</div>
<script>
async function refresh(){
  try{
    const r=await fetch('/api/stats');const d=await r.json();
    document.getElementById('stats').innerHTML=
      `<div class="stat"><div class="value">${d.total_agents}</div><div class="label">Online Agents</div></div>
       <div class="stat"><div class="value">${d.skills?.length||0}</div><div class="label">Skills</div></div>
       <div class="stat"><div class="value">${d.total_agents}</div><div class="label">Ready</div></div>`;
    if(d.agents){
      document.getElementById('agents').innerHTML=d.agents.map(a=>
        `<tr><td>${a.name}</td><td>${(a.skills||[]).join(', ')}</td><td>${((a.reputation||0.5)*100).toFixed(0)}%</td></tr>`
      ).join('');
    }
  }catch(e){}
}
refresh();setInterval(refresh,10000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._html(HTML)
        elif self.path == "/api/stats":
            self._json(node.stats())
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path == "/api/announce":
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len)) if content_len > 0 else {}
            agent = body.get("agent", {})
            port = body.get("port", 0)
            # Register via TCP to local node
            from discovery_node import AgentEntry
            import time
            entry = AgentEntry(
                agent_id=agent.get("agent_id", ""),
                name=agent.get("name", ""),
                skills=agent.get("skills", []),
                host=self.client_address[0],
                port=port,
                wallet=agent.get("wallet_address", ""),
                reputation=agent.get("reputation", 0.5),
            )
            node._agents[entry.agent_id] = entry
            self._json({"status": "registered"})
        else:
            self.send_response(404); self.end_headers()

    def _html(self, h):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(h.encode())

    def _json(self, d):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(d).encode())


if __name__ == "__main__":
    import os, threading
    web_port = int(os.environ.get("PORT", 8888))
    threading.Thread(target=node.start, daemon=True).start()
    dash = HTTPServer(("0.0.0.0", web_port), Handler)
    print(f"Dashboard: http://0.0.0.0:{web_port}")
    dash.serve_forever()
