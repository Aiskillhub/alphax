#!/usr/bin/env python3
"""AlphaX Web 配置面板 — 浏览器里填，保存到 .env"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).parent
ENV_PATH = ROOT / ".env"

SETUP_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AlphaX 配置</title>
<style>
:root{--bg:#0b0f19;--card:#111827;--border:#1f2937;--text:#f1f5f9;--muted:#9ca3af;--accent:#6366f1;--green:#10b981;--red:#ef4444;--radius:12px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
body::before{content:'';position:fixed;inset:0;background:radial-gradient(circle at 20% 20%,rgba(99,102,241,.08),transparent 50%),radial-gradient(circle at 80% 80%,rgba(139,92,246,.06),transparent 50%)}
.container{position:relative;z-index:1;width:100%;max-width:560px}
.header{text-align:center;margin-bottom:32px}
.header h1{font-size:28px;font-weight:800;letter-spacing:-.02em}
.header h1 span{background:linear-gradient(135deg,#818cf8,#c084fc);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header p{color:var(--muted);margin-top:6px;font-size:14px}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:28px;margin-bottom:16px}
.card h2{font-size:14px;font-weight:600;margin-bottom:16px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
.field{margin-bottom:16px}
.field:last-child{margin-bottom:0}
.field label{display:block;font-size:12px;font-weight:500;color:var(--muted);margin-bottom:5px;text-transform:uppercase;letter-spacing:.04em}
.field input{width:100%;padding:10px 14px;background:#1a1f2e;border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:14px;font-family:'SF Mono',Monaco,monospace;outline:none;transition:border-color .15s}
.field input:focus{border-color:var(--accent)}
.field input::placeholder{color:#4b5563}
.hint{font-size:11px;color:#6b7280;margin-top:4px}
.required label::after{content:' *';color:var(--red)}
.toast{position:fixed;top:20px;left:50%;transform:translateX(-50%);padding:12px 24px;border-radius:8px;font-size:14px;font-weight:500;z-index:100;transition:all .3s;pointer-events:none;opacity:0}
.toast.show{opacity:1}
.toast.success{background:#065f46;color:#d1fae5}
.toast.error{background:#7f1d1d;color:#fecaca}
.btn-row{display:flex;gap:12px;margin-top:24px}
.btn{padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;border:none;transition:all .15s;flex:1}
.btn-primary{background:linear-gradient(135deg,var(--accent),#8b5cf6);color:#fff}
.btn-primary:hover{box-shadow:0 4px 20px rgba(99,102,241,.35);transform:translateY(-1px)}
.btn-secondary{background:transparent;border:1px solid var(--border);color:var(--muted)}
.btn-secondary:hover{border-color:var(--accent);color:var(--text)}
.status{text-align:center;font-size:12px;color:var(--muted);margin-top:20px}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Alpha X <span>配置面板</span></h1>
    <p>填入 API 密钥后保存，写入 .env 文件</p>
  </div>

  <div class="card">
    <h2>LLM API（必填）</h2>
    <div class="field required">
      <label>API Key</label>
      <input id="deepseek_api_key" placeholder="sk-xxx">
    </div>
    <div class="field">
      <label>Base URL</label>
      <input id="deepseek_base_url" placeholder="https://api.deepseek.com">
    </div>
  </div>

  <div class="card">
    <h2>市场渠道</h2>
    <div class="field">
      <label>Gumroad Access Token</label>
      <input id="gumroad_access_token" placeholder="Gumroad API token">
    </div>
    <div class="field">
      <label>AGIStore API Token</label>
      <input id="agistore_api_token" placeholder="AGIStore token">
    </div>
    <div class="field">
      <label>AGIStore URL</label>
      <input id="agistore_api_url" placeholder="http://localhost:3005">
    </div>
  </div>

  <div class="card">
    <h2>支付</h2>
    <div class="field">
      <label>Stripe Secret Key</label>
      <input id="stripe_secret_key" placeholder="sk_test_xxx">
    </div>
    <div class="field">
      <label>Stripe Webhook Secret</label>
      <input id="stripe_webhook_secret" placeholder="whsec_xxx">
    </div>
  </div>

  <div class="btn-row">
    <button class="btn btn-secondary" onclick="loadCurrent()">加载当前配置</button>
    <button class="btn btn-primary" onclick="save()">保存配置</button>
  </div>
  <div class="status" id="status"></div>
</div>

<div class="toast" id="toast"></div>

<script>
var fields=['deepseek_api_key','deepseek_base_url','gumroad_access_token','agistore_api_token',
  'agistore_api_url','stripe_secret_key','stripe_webhook_secret'];

function toast(msg,type){
  var t=document.getElementById('toast');
  t.textContent=msg;t.className='toast '+type+' show';
  setTimeout(function(){t.classList.remove('show')},2500);
}

async function loadCurrent(){
  try{
    var r=await fetch('/api/current');
    var d=await r.json();
    for(var k in d){var el=document.getElementById(k);if(el)el.value=d[k]||''}
    toast('已加载当前配置','success');
  }catch(e){toast('加载失败: '+e.message,'error')}
}

async function save(){
  var data={};
  for(var i=0;i<fields.length;i++){
    var el=document.getElementById(fields[i]);
    if(el&&el.value.trim())data[fields[i]]=el.value.trim();
  }
  if(!data.deepseek_api_key){toast('请填写 API Key','error');return}
  try{
    var r=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    var d=await r.json();
    if(d.ok){toast('配置已保存到 .env','success');document.getElementById('status').textContent='✅ 已保存 — 现在可以运行 python3 main.py'}
    else{toast(d.error||'保存失败','error')}
  }catch(e){toast('保存失败: '+e.message,'error')}
}

loadCurrent();
</script>
</body>
</html>"""


class SetupHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self._html(SETUP_HTML)
        elif path == "/api/current":
            self._json(self._read_current())
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/save":
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self._save_config(body)
            self._json({"ok": True})
        else:
            self._json({"error": "not found"}, 404)

    def _read_current(self) -> dict:
        data = {}
        if ENV_PATH.exists():
            for line in ENV_PATH.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k = k.strip().lower()
                    v = v.strip().strip('"').strip("'")
                    if v:
                        data[k] = v
        return data

    def _save_config(self, data: dict):
        lines = ["# AlphaX 配置"]
        section = None
        field_sections = {
            "deepseek_api_key": "LLM API", "deepseek_base_url": "LLM API",
            "gumroad_access_token": "市场渠道", "agistore_api_token": "市场渠道",
            "agistore_api_url": "市场渠道",
            "stripe_secret_key": "支付", "stripe_webhook_secret": "支付",
        }
        seen = set()
        for section_name in ["LLM API", "市场渠道", "支付"]:
            section_fields = [k for k, v in field_sections.items() if v == section_name]
            values = [(k.upper(), data[k]) for k in section_fields if k in data and data[k]]
            if values:
                lines.append(f"\n# ── {section_name} ──")
                for k, v in values:
                    lines.append(f"{k}={v}")
                    seen.add(k.upper())

        ENV_PATH.write_text("\n".join(lines) + "\n")

    def _html(self, content: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode())

    def _json(self, data: dict, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = 8088
    print(f"\n  ╔══════════════════════════════════╗")
    print(f"  ║  Alpha X 配置面板              ║")
    print(f"  ╚══════════════════════════════════╝")
    print(f"\n  🌐 打开浏览器 → http://localhost:{port}")
    print(f"  填写后保存，自动写入 .env\n")
    HTTPServer(("0.0.0.0", port), SetupHandler).serve_forever()
