"""AlphaX — AI 帮你做工具，$49/个

一条命令启动：
  python3 product_page.py
  open http://localhost:8877
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

import sys; sys.path.insert(0, str(Path(__file__).parent))

from config import config
from intent_parser import IntentParser
from judge import Judge
from arena_models import ArenaTask, ArenaProgress
from arena import Arena
from screenshot import capture_zip


# ── 订单状态 ──

class Orders:
    def __init__(self):
        self._orders: dict[str, dict] = {}

    def create(self, description: str, product_type: str, agents: int, gens: int) -> str:
        oid = uuid.uuid4().hex[:8]
        self._orders[oid] = {
            "id": oid,
            "description": description,
            "product_type": product_type,
            "status": "created",
            "progress": {"phase": "idle"},
            "result": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return oid

    def update(self, oid: str, **kw):
        if oid in self._orders:
            self._orders[oid].update(kw)

    def get(self, oid: str) -> dict | None:
        return self._orders.get(oid)


orders = Orders()


# ── HTTP ──

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._html()
        elif path.startswith("/api/order/"):
            oid = path.rsplit("/", 1)[-1]
            self._json(orders.get(oid) or {"error": "not found"})
        elif path.startswith("/api/download/"):
            oid = path.rsplit("/", 1)[-1]
            self._download(oid)
        elif path.startswith("/preview/"):
            fname = path.rsplit("/", 1)[-1]
            self._serve_preview(fname)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path == "/api/order":
            self._create_order()
        else:
            self.send_response(404); self.end_headers()

    def _create_order(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        desc = body.get("description", "").strip()
        ptype = body.get("product_type", "web_tool")
        agents = int(body.get("agents", 8))
        gens = int(body.get("gens", 2))

        if not desc:
            return self._json({"error": "请填写需求描述"}, 400)

        oid = orders.create(desc, ptype, agents, gens)

        # 后台跑 Arena
        def run():
            orders.update(oid, status="running")
            try:
                arena = Arena()
                result = arena.run(
                    description=desc,
                    product_type=ptype,
                    n_agents=agents,
                    n_generations=gens,
                    on_progress=lambda p: orders.update(oid, progress={
                        "phase": p.phase, "generation": p.generation,
                        "agents_done": p.agents_completed,
                        "total_agents": p.total_agents,
                        "current": p.current_action,
                        "top": p.top_so_far,
                        "score": p.top_score_so_far,
                    }),
                )
                # 截图
                from pathlib import Path
                ss = capture_zip(Path(result.winner_code_path)) if result.winner_code_path else None
                orders.update(oid, status="done", result={
                    "name": result.winner_name,
                    "score": result.winner_score,
                    "code_path": result.winner_code_path,
                    "screenshot": str(ss) if ss else "",
                    "generations": result.total_generations,
                    "duration": result.total_duration_seconds,
                })
            except Exception as e:
                orders.update(oid, status="failed", result={"error": str(e)})

        threading.Thread(target=run, daemon=True).start()
        self._json({"order_id": oid, "status": "started"})

    def _download(self, oid):
        data = orders.get(oid)
        if not data or not data.get("result"):
            self.send_response(404); self.end_headers(); return
        path = data["result"].get("code_path", "")
        if not path or not Path(path).exists():
            self.send_response(404); self.end_headers(); return
        p = Path(path)
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{p.name}"')
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(p.read_bytes())

    def _serve_preview(self, fname):
        import zipfile
        p = Path(__file__).parent / "data" / "builds" / fname
        if not p.exists():
            self.send_response(404); self.end_headers(); return
        try:
            with zipfile.ZipFile(p) as zf:
                for name in zf.namelist():
                    if name.endswith(".html"):
                        content = zf.read(name)
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(content)
                        return
            self.send_response(404); self.end_headers()
        except Exception:
            self.send_response(500); self.end_headers()

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _html(self):
        html = r"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AlphaX — AI 帮你做工具，$49/个</title><style>
:root{--bg:#0a0a0f;--card:#131320;--border:#1e1e35;--text:#e0e0e8;--muted:#6b6b80;--accent:#6366f1;--green:#22c55e;--amber:#f59e0b;--red:#ef4444}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.container{max-width:560px;width:100%}
h1{font-size:32px;font-weight:800;letter-spacing:-1px;margin-bottom:4px}
h1 span{background:linear-gradient(135deg,var(--accent),#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sub{color:var(--muted);font-size:15px;margin-bottom:32px;line-height:1.6}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:24px;margin-bottom:16px}
label{display:block;font-size:13px;font-weight:500;margin-bottom:8px;color:var(--muted)}
select,input,textarea{width:100%;padding:12px 16px;background:var(--bg);border:1px solid var(--border);border-radius:10px;color:var(--text);font-size:15px;font-family:inherit;outline:none;margin-bottom:16px}
select:focus,input:focus,textarea:focus{border-color:var(--accent)}
textarea{min-height:100px;resize:vertical}
.row{display:flex;gap:12px}.row>*{flex:1}
.btn{width:100%;padding:14px;border:none;border-radius:10px;font-size:16px;font-weight:700;cursor:pointer;transition:all .15s}
.btn-primary{background:var(--accent);color:#fff}
.btn-primary:hover{opacity:.9}
.btn-primary:disabled{opacity:.5;cursor:not-allowed}
.price{text-align:center;color:var(--green);font-size:36px;font-weight:900;margin:8px 0 4px}
.price-sub{text-align:center;color:var(--muted);font-size:13px;margin-bottom:16px}
/* 进度 */
.progress{display:none;text-align:center}
.progress.active{display:block}
.progress-bar{height:6px;background:var(--border);border-radius:3px;margin:16px 0;overflow:hidden}
.progress-fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--green));border-radius:3px;transition:width .3s;width:0%}
.status-line{font-size:14px;color:var(--amber);margin:8px 0}
.top-line{font-size:13px;color:var(--accent);margin:4px 0}
/* 结果 */
.result{display:none}
.result.active{display:block}
.result-card{background:linear-gradient(135deg,#1a1530,#0d2818);border:1px solid var(--accent);border-radius:16px;padding:24px;text-align:center}
.result-card .name{font-size:22px;font-weight:700;margin-bottom:4px}
.result-card .score{font-size:48px;font-weight:900;color:var(--green)}
.result-card .meta{color:var(--muted);font-size:13px;margin-top:8px}
.btns{display:flex;gap:12px;margin-top:16px}
.btns .btn{flex:1;font-size:14px;padding:12px}
.btn-outline{background:var(--card);border:1px solid var(--border);color:var(--text);cursor:pointer}
</style></head><body>
<div class="container">
<h1>AlphaX — <span>AI 帮你做工具</span></h1>
<p class="sub">描述你想要什么。10 个 AI Agent 竞争，自动选出最优方案。不满意不要钱。</p>

<div class="card" id="formCard">
  <label>产品类型</label>
  <select id="ptype">
    <option value="web_tool">🌐 网页工具（计算器、格式化器、生成器）</option>
    <option value="chrome_extension">🧩 Chrome 浏览器扩展</option>
    <option value="prompt_library">📝 AI 提示词包（50条）</option>
  </select>
  <label>描述你想要什么</label>
  <textarea id="desc" placeholder="比如：一个房贷计算器，输入金额、利率、年限，显示每月还款和总利息"></textarea>
  <div class="row">
    <div><label>Agent 数</label><input type="number" id="agents" value="8" min="4" max="20"></div>
    <div><label>进化代数</label><input type="number" id="gens" value="2" min="1" max="5"></div>
  </div>
  <div class="price">$49</div>
  <div class="price-sub">不满意全额退款</div>
  <button class="btn btn-primary" id="startBtn" onclick="start()">⚡ 开始生成</button>
</div>

<div class="card progress" id="progressCard">
  <div class="status-line" id="statusLine">准备中…</div>
  <div class="progress-bar"><div class="progress-fill" id="bar"></div></div>
  <div class="top-line" id="topLine"></div>
  <div id="agentDots" style="display:flex;gap:4px;justify-content:center;margin-top:12px"></div>
</div>

<div class="result card" id="resultCard">
  <div class="result-card">
    <div class="name" id="rName">—</div>
    <div class="score" id="rScore">—</div>
    <div class="meta" id="rMeta"></div>
  </div>
  <div class="btns">
    <button class="btn btn-outline" id="previewBtn" style="display:none" onclick="preview()">👁 在线预览</button>
    <button class="btn btn-primary" id="downloadBtn" onclick="downloadZip()">📥 下载</button>
    <button class="btn btn-outline" onclick="reset_()">🔄 再来一个</button>
  </div>
</div>
</div>
<script>
let orderId='',codePath='',timer=null;

function start(){
  let desc=document.getElementById('desc').value.trim();
  if(!desc)return alert('请填写需求描述');
  document.getElementById('startBtn').disabled=true;
  document.getElementById('startBtn').textContent='⏳ 提交中…';
  fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({description:desc,product_type:document.getElementById('ptype').value,
      agents:parseInt(document.getElementById('agents').value)||8,
      gens:parseInt(document.getElementById('gens').value)||2})})
  .then(r=>r.json()).then(d=>{
    if(d.error){alert(d.error);resetBtn();return}
    orderId=d.order_id;
    document.getElementById('formCard').style.display='none';
    document.getElementById('progressCard').classList.add('active');
    poll();
  }).catch(e=>{alert('提交失败');resetBtn();});
}

function poll(){
  fetch('/api/order/'+orderId).then(r=>r.json()).then(d=>{
    if(!d||d.error)return;
    let p=d.progress||{};
    if(d.status==='done'){showResult(d.result);return}
    if(d.status==='failed'){alert('生成失败: '+(d.result||{}).error);reset_();return}
    updateProgress(p);
    timer=setTimeout(poll,2000);
  }).catch(()=>{timer=setTimeout(poll,3000);});
}

function updateProgress(p){
  let total=p.total_agents||8, done=p.agents_done||0;
  let pct=total>0?Math.round(done/total*100):0;
  document.getElementById('bar').style.width=pct+'%';
  document.getElementById('statusLine').textContent=p.current||('Agent '+done+'/'+total+' 正在生成…');
  if(p.top)document.getElementById('topLine').textContent='🏆 当前最佳: '+p.top+' ('+(p.score||0)+'分)';
  // dots
  let dots=document.getElementById('agentDots');dots.innerHTML='';
  for(let i=0;i<total;i++){let d=document.createElement('span');d.style.cssText='width:8px;height:8px;border-radius:50%;background:'+(i<done?'var(--green)':i===done?'var(--amber)':'var(--border)');if(i===done&&p.phase!=='done')d.style.animation='pulse .6s infinite';dots.appendChild(d);}
}

function showResult(r){
  clearTimeout(timer);
  document.getElementById('progressCard').classList.remove('active');
  document.getElementById('resultCard').classList.add('active');
  document.getElementById('rName').textContent=r.name||'—';
  document.getElementById('rScore').textContent=(r.score||0)+' 分';
  document.getElementById('rMeta').textContent=(r.generations||0)+'代进化 · '+(r.duration||0)+'秒';
  codePath=r.code_path||'';
  document.getElementById('previewBtn').style.display=codePath?'':'none';
}

function preview(){
  if(!codePath)return;
  let fname=codePath.split('/').pop();
  window.open('/preview/'+fname,'_blank');
}
function downloadZip(){
  if(!orderId)return;
  window.open('/api/download/'+orderId,'_blank');
}
function reset_(){clearTimeout(timer);orderId='';codePath='';
  document.getElementById('formCard').style.display='';document.getElementById('progressCard').classList.remove('active');
  document.getElementById('resultCard').classList.remove('active');resetBtn();}
function resetBtn(){document.getElementById('startBtn').disabled=false;document.getElementById('startBtn').textContent='⚡ 开始生成';}
</script></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, *a): pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8877)
    args = parser.parse_args()
    print(f"🚀 AlphaX Product Page → http://localhost:{args.port}")
    HTTPServer(("0.0.0.0", args.port), Handler).serve_forever()
