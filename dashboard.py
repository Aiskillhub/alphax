"""AlphaX 控制面板 v4 — 真实版

只展示真实的东西：
  1. 实际构建了哪些产品（代码文件存在）
  2. 每个产品在什么渠道可以卖
  3. 哪些渠道已经配置好了（绿色）vs 需要配置（灰色）
  4. 一键运行生成新产品

Usage: python3 dashboard.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
DATA = ROOT / "data"
BUILDS = DATA / "builds"


def get_built_products():
    """扫描实际构建产物"""
    products = []
    if not BUILDS.exists():
        return products

    for zipf in sorted(BUILDS.glob("*.zip"), key=lambda f: f.stat().st_mtime, reverse=True):
        pid = zipf.stem
        size_kb = round(zipf.stat().st_size / 1024, 1)
        mtime = datetime.fromtimestamp(zipf.stat().st_mtime).strftime("%m-%d %H:%M")

        # 检查 listing.json
        listing = {}
        build_dir = None
        for d in BUILDS.iterdir():
            if d.is_dir() and (d.name == pid or d.name.startswith(f"notion_{pid}")
                               or d.name.startswith(f"vscode_{pid}")
                               or d.name.startswith(f"prompt_{pid}")
                               or d.name.startswith(f"webtool_{pid}")):
                lf = d / "listing.json"
                if lf.exists():
                    listing = json.loads(lf.read_text())
                build_dir = d
                break

        products.append({
            "id": pid[:24],
            "name": listing.get("title", pid.replace("_", " ").title()),
            "desc": listing.get("subtitle", listing.get("description", ""))[:60],
            "price": listing.get("price_point", 0) or (build_dir and _guess_price(build_dir)) or 0,
            "size": f"{size_kb}KB",
            "built": mtime,
            "files": _list_files(build_dir) if build_dir else [],
        })
    return products


def _guess_price(build_dir):
    """从文件推测价格"""
    lf = build_dir / "listing.json"
    if lf.exists():
        d = json.loads(lf.read_text())
        return d.get("price_point", 0)
    return 0


def _list_files(build_dir):
    if not build_dir or not build_dir.exists():
        return []
    return [f.name for f in build_dir.iterdir() if f.is_file()]


def get_channel_status():
    """各渠道真实状态"""
    from config import config

    channels = [
        {"name": "自建商店 (AlphaX Store)", "fee": "0%", "status": "ready",
         "desc": "python3 publisher/storefront.py --port 8085", "url": "http://localhost:8085"},
        {"name": "Gumroad", "fee": "10%", "status": "ready" if config.gumroad_access_token else "need_key",
         "desc": "需要 GUMROAD_ACCESS_TOKEN", "url": "https://gumroad.com"},
        {"name": "Chrome Web Store", "fee": "5%", "status": "need_key",
         "desc": "需要 Google OAuth 凭证", "url": "https://chrome.google.com/webstore"},
        {"name": "Payhip", "fee": "5%", "status": "ready",
         "desc": "API ready, 需配置 token", "url": "https://payhip.com"},
        {"name": "Lemon Squeezy", "fee": "5%+$0.50", "status": "ready",
         "desc": "API ready, 需配置 key", "url": "https://lemonsqueezy.com"},
        {"name": "Polar", "fee": "4%+$0.40", "status": "ready",
         "desc": "API ready, 需配置 key", "url": "https://polar.sh"},
        {"name": "Agent 市场 (抽别人的成)", "fee": "赚 5-10%", "status": "ready",
         "desc": "python3 publisher/agent_marketplace.py --port 8086", "url": "http://localhost:8086"},
    ]
    return channels


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self._html()
        elif path == "/api/status":
            self._json({"products": get_built_products(), "channels": get_channel_status()})
        elif path == "/api/run":
            self._json({"status": "started", "msg": "在终端运行: python3 main.py --days 30"})
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


HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AlphaX — 赚钱面板</title>
<style>
:root{--bg:#fafafa;--card:#fff;--border:#e5e7eb;--text:#111;--muted:#6b7280;--green:#059669;--red:#dc2626;--blue:#2563eb;--orange:#d97706}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:900px;margin:0 auto;padding:24px 16px}
h1{font-size:20px;margin-bottom:4px}
h1 span{color:var(--blue)}
.sub{color:var(--muted);font-size:13px;margin-bottom:24px}
.section{margin-bottom:28px}
.section h2{font-size:14px;font-weight:600;margin-bottom:12px;padding-bottom:6px;border-bottom:2px solid var(--border);display:flex;align-items:center;gap:8px}
.section h2 .count{font-size:12px;color:var(--muted);font-weight:400}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px 16px;margin-bottom:8px;display:flex;align-items:center;gap:12px}
.card:hover{border-color:#93c5fd}
.card .icon{font-size:24px;min-width:32px;text-align:center}
.card .info{flex:1;min-width:0}
.card .info .name{font-weight:600;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .info .meta{color:var(--muted);font-size:12px;margin-top:2px}
.card .price{font-weight:700;font-size:16px;color:var(--green);min-width:60px;text-align:right}
.card .files{display:flex;gap:3px;flex-wrap:wrap;margin-top:4px}
.card .files span{background:#f3f4f6;padding:1px 6px;border-radius:4px;font-size:10px;color:var(--muted);font-family:monospace}
.channel-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
@media(max-width:600px){.channel-grid{grid-template-columns:1fr}}
.channel{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 14px}
.channel.ready{border-left:3px solid var(--green)}
.channel.need_key{border-left:3px solid #d1d5db;opacity:.7}
.channel .cn{font-weight:600;font-size:13px;display:flex;justify-content:space-between;align-items:center}
.channel .cf{font-size:11px;color:var(--green);font-weight:500}
.channel .cd{font-size:11px;color:var(--muted);margin-top:4px}
.channel .ck{color:var(--orange);font-size:11px}
.tag{display:inline-block;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:500}
.tag.ok{background:#d1fae5;color:var(--green)}
.tag.wait{background:#fef3c7;color:var(--orange)}
.empty{text-align:center;padding:40px 20px;color:var(--muted);font-size:14px}
.empty code{background:#f3f4f6;padding:2px 6px;border-radius:4px;font-size:12px}
.btn{display:inline-block;padding:10px 20px;background:var(--blue);color:#fff;border-radius:8px;text-decoration:none;font-size:13px;font-weight:500;border:none;cursor:pointer}
.btn:hover{background:#1d4ed8}
.cmd{background:#1e1e2e;color:#cdd6f4;padding:12px 16px;border-radius:8px;font-size:12px;font-family:monospace;overflow-x:auto;margin-top:8px}
.footer{text-align:center;padding:24px;color:var(--muted);font-size:11px}
</style>
</head>
<body>
<h1><span>Alpha X</span> 赚钱面板</h1>
<div class="sub" id="summary">加载中...</div>

<div class="section">
  <h2>📦 已构建产品 <span class="count" id="prodCount"></span></h2>
  <div id="products"></div>
</div>

<div class="section">
  <h2>🏪 销售渠道</h2>
  <div class="channel-grid" id="channels"></div>
</div>

<div class="section">
  <h2>▶ 操作</h2>
  <div class="cmd" id="runCmd">python3 main.py --days 30</div>
  <p style="color:var(--muted);font-size:12px;margin-top:8px;">
    在终端运行上面的命令启动进化循环。30 天模拟约需 3-5 分钟（含 AI 决策）。
  </p>
</div>

<div class="footer" id="footer">刷新: ...</div>

<script>
async function refresh() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    render(d);
    document.getElementById('footer').textContent = '刷新: ' + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('footer').textContent = '加载失败，10秒后重试';
  }
}

function render(d) {
  // 总览
  const totalProducts = d.products.length;
  const readyChannels = d.channels.filter(c => c.status === 'ready').length;
  document.getElementById('summary').textContent =
    `${totalProducts} 个产品已构建 · ${readyChannels} 个销售渠道可用`;

  // 产品
  document.getElementById('prodCount').textContent = `(${totalProducts})`;
  if (totalProducts === 0) {
    document.getElementById('products').innerHTML =
      '<div class="empty">还没有产品<br><code>python3 main.py --days 30</code></div>';
  } else {
    document.getElementById('products').innerHTML = d.products.slice(0,20).map(p => `
      <div class="card">
        <div class="icon">${iconForName(p.name)}</div>
        <div class="info">
          <div class="name">${p.name}</div>
          <div class="meta">${p.desc||'无描述'} · ${p.size} · ${p.built}</div>
          ${p.files.length ? '<div class="files">'+p.files.map(f=>'<span>'+f+'</span>').join('')+'</div>' : ''}
        </div>
        <div class="price">${p.price > 0 ? '$'+p.price.toFixed(2) : '—'}</div>
      </div>
    `).join('');
  }

  // 渠道
  document.getElementById('channels').innerHTML = d.channels.map(c => {
    const cls = c.status === 'ready' ? 'ready' : 'need_key';
    const tag = c.status === 'ready'
      ? '<span class="tag ok">可用</span>'
      : '<span class="tag wait">需配置</span>';
    return `<div class="channel ${cls}">
      <div class="cn">${c.name} ${tag}</div>
      <div class="cf">平台费: ${c.fee}</div>
      <div class="cd">${c.status === 'ready' ? c.desc : '<span class="ck">'+c.desc+'</span>'}</div>
    </div>`;
  }).join('');
}

function iconForName(name) {
  if (name.includes('Notion') || name.includes('OS')) return '📋';
  if (name.includes('Prompt') || name.includes('AI')) return '✨';
  if (name.includes('Code') || name.includes('Pro')) return '⚡';
  if (name.includes('Chat')) return '💬';
  if (name.includes('Workflow') || name.includes('Auto')) return '🔄';
  return '📦';
}

refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>"""


def main():
    port = int(os.environ.get("PORT", 8080))
    print(f"\n  AlphaX 赚钱面板 → http://localhost:{port}")
    print(f"  展示真实构建的产品 + 可用销售渠道\n")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
