"""AlphaX Arena — Web 服务器 + 前端界面

一条命令启动:
  python3 arena_server.py
  python3 arena_server.py --port 8899

打开浏览器 → http://localhost:8899
"""

from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).parent))

from arena import Arena
from arena_models import ArenaProgress, ArenaResult


# ═══════════════════════════════════════════════
# 内存状态
# ═══════════════════════════════════════════════

class State:
    def __init__(self):
        self._lock = threading.Lock()
        self.tasks: dict[str, dict] = {}  # task_id → {progress, result, running}

    def create_task(self) -> str:
        tid = uuid.uuid4().hex[:8]
        with self._lock:
            self.tasks[tid] = {
                "progress": ArenaProgress().__dict__,
                "result": None,
                "running": True,
            }
        return tid

    def update_progress(self, tid: str, progress: ArenaProgress):
        with self._lock:
            if tid in self.tasks:
                self.tasks[tid]["progress"] = progress.__dict__

    def set_result(self, tid: str, result: ArenaResult):
        with self._lock:
            if tid in self.tasks:
                self.tasks[tid]["result"] = result.__dict__
                self.tasks[tid]["running"] = False

    def get(self, tid: str) -> dict | None:
        with self._lock:
            return self.tasks.get(tid)


state = State()


# ═══════════════════════════════════════════════
# HTTP 处理
# ═══════════════════════════════════════════════

class ArenaHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # 静默

    # ── 路由 ──

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            return self._serve_html()

        if path.startswith("/api/arena/progress/"):
            tid = path.rsplit("/", 1)[-1]
            return self._json_response(state.get(tid) or {"error": "not found"})

        if path.startswith("/api/arena/result/"):
            tid = path.rsplit("/", 1)[-1]
            data = state.get(tid)
            if not data or not data.get("result"):
                return self._json_response({"error": "not ready"}, 404)
            return self._json_response(data)

        if path.startswith("/api/builds/"):
            fname = path.rsplit("/", 1)[-1]
            return self._serve_build(fname)

        if path.startswith("/preview/"):
            fname = path.rsplit("/", 1)[-1]
            return self._serve_preview(fname)

        if path.startswith("/screenshots/"):
            fname = path.rsplit("/", 1)[-1]
            return self._serve_screenshot(fname)

        return self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/arena/run":
            return self._handle_run()

        if path == "/api/arena/list-builds":
            return self._handle_list_builds()

        return self._json_response({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self._cors_headers()
        self.send_response(204)
        self.end_headers()

    # ── 业务 ──

    def _handle_run(self):
        body = self._read_body()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}

        description = data.get("description", "")
        product_type = data.get("product_type", "web_tool")
        n_agents = int(data.get("agents", 10))
        n_gens = int(data.get("gens", 3))
        api_key = data.get("api_key", "").strip()

        if not description.strip():
            return self._json_response({"error": "请填写需求描述"}, 400)

        tid = state.create_task()

        def callback(p: ArenaProgress):
            state.update_progress(tid, p)

        def run_in_thread():
            try:
                arena = Arena(api_key=api_key)
                result = arena.run(
                    description=description,
                    product_type=product_type,
                    n_agents=n_agents,
                    n_generations=n_gens,
                    on_progress=callback,
                )
                state.set_result(tid, result)
            except Exception as e:
                state.set_result(tid, ArenaResult())
                state.update_progress(tid, ArenaProgress(error=str(e), is_done=True))

        threading.Thread(target=run_in_thread, daemon=True).start()

        return self._json_response({"task_id": tid, "status": "started"})

    def _handle_list_builds(self):
        builds_dir = Path(__file__).parent / "data" / "builds"
        files = []
        if builds_dir.exists():
            for f in sorted(builds_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
                if f.suffix == ".zip":
                    files.append({
                        "name": f.name,
                        "size_kb": round(f.stat().st_size / 1024, 1),
                        "path": str(f),
                    })
        return self._json_response({"builds": files})

    def _serve_build(self, fname: str):
        """下载生成的文件。"""
        p = Path(__file__).parent / "data" / "builds" / fname
        if not p.exists() or not p.is_file():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
        self._cors_headers()
        self.end_headers()
        self.wfile.write(p.read_bytes())

    def _serve_preview(self, fname: str):
        """提取并在线预览生成的 Web 工具。"""
        import zipfile, io
        p = Path(__file__).parent / "data" / "builds" / fname
        if not p.exists():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")
            return
        try:
            with zipfile.ZipFile(p) as zf:
                # 找 HTML 文件
                html_name = None
                for name in zf.namelist():
                    if name.endswith(".html"):
                        html_name = name
                        break
                if not html_name:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"no html file in zip")
                    return
                content = zf.read(html_name).decode("utf-8", errors="replace")
        except Exception:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"extract failed")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(content.encode())

    def _serve_screenshot(self, fname: str):
        """返回截图文件。"""
        p = Path(__file__).parent / "data" / "builds" / fname
        if not p.exists():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Cache-Control", "no-cache")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(p.read_bytes())

    # ── 辅助 ──

    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(HTML.encode())

    def _json_response(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())

    def _read_body(self) -> str:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode() if length else ""

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


# ═══════════════════════════════════════════════
# 前端 HTML
# ═══════════════════════════════════════════════

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AlphaX Arena — Agent 竞技场</title>
<style>
:root{--bg:#0a0a0f;--card:#131320;--border:#1e1e35;--text:#e0e0e8;--muted:#6b6b80;--accent:#6366f1;--accent2:#818cf8;--green:#22c55e;--red:#ef4444;--amber:#f59e0b}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",sans-serif;background:var(--bg);color:var(--text);min-height:100vh;line-height:1.5}
.container{max-width:800px;margin:0 auto;padding:40px 20px}
h1{font-size:28px;font-weight:700;letter-spacing:-0.5px;margin-bottom:8px;background:linear-gradient(135deg,var(--accent2),var(--accent));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.subtitle{color:var(--muted);font-size:15px;margin-bottom:32px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px;margin-bottom:16px}
.card-title{font-size:14px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:16px}
.form-group{margin-bottom:16px}
label{display:block;font-size:13px;font-weight:500;margin-bottom:6px;color:var(--muted)}
input,textarea,select{width:100%;padding:10px 14px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:14px;font-family:inherit;outline:none;transition:border-color .15s}
input:focus,textarea:focus,select:focus{border-color:var(--accent)}
textarea{resize:vertical;min-height:80px}
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 24px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;transition:all .15s}
.btn-primary{background:var(--accent);color:#fff}
.btn-primary:hover{background:var(--accent2)}
.btn-primary:disabled{opacity:.5;cursor:not-allowed}
.row{display:flex;gap:12px}
.row>*{flex:1}

/* 进度区 */
.progress-panel{display:none}
.progress-panel.active{display:block}
.phase-badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600}
.phase-parsing{background:#1e1e35;color:var(--amber)}
.phase-building{background:#1e1e35;color:var(--accent2)}
.phase-judging{background:#1e1e35;color:var(--accent2)}
.phase-evolving{background:#1e1e35;color:var(--green)}
.phase-done{background:#0d2818;color:var(--green)}
.bar-track{height:6px;background:var(--border);border-radius:3px;margin:16px 0;overflow:hidden}
.bar-fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--green));border-radius:3px;transition:width .3s}
.agent-list{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}
.agent-dot{width:8px;height:8px;border-radius:50%;background:var(--border);transition:background .2s}
.agent-dot.done{background:var(--green)}
.agent-dot.current{background:var(--accent);animation:pulse .6s infinite}
@keyframes pulse{50%{opacity:.4}}

/* 结果区 */
.result-panel{display:none}
.result-panel.active{display:block}
.winner-card{background:linear-gradient(135deg,#1a1530,#0d2818);border:1px solid var(--accent);border-radius:12px;padding:24px;text-align:center}
.winner-icon{font-size:48px;margin-bottom:8px}
.winner-name{font-size:20px;font-weight:700;margin-bottom:4px}
.winner-score{font-size:36px;font-weight:800;color:var(--green)}
.score-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:16px}
.score-item{text-align:center}
.score-val{font-size:24px;font-weight:700}
.score-label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.rank-table{width:100%;border-collapse:collapse;margin-top:12px}
.rank-table th{text-align:left;font-size:11px;color:var(--muted);text-transform:uppercase;padding:8px 12px;border-bottom:1px solid var(--border)}
.rank-table td{padding:10px 12px;border-bottom:1px solid var(--border);font-size:13px}
.rank-table tr:hover{background:rgba(255,255,255,.02)}
.medal{font-size:16px}

/* 错误 */
.error-msg{background:rgba(239,68,68,.1);border:1px solid var(--red);border-radius:8px;padding:12px 16px;color:var(--red);font-size:13px;margin-top:12px}

/* 生成记录 */
.built-item{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);font-size:13px}
.built-item:last-child{border-bottom:none}
</style>
</head>
<body>
<div class="container">
  <h1>AlphaX Arena</h1>
  <p class="subtitle">10 个 AI Agent 竞争，优胜劣汰，只交付最优方案</p>

  <!-- 输入卡片 -->
  <div class="card" id="inputCard">
    <div class="card-title">🎯 描述你想要什么</div>
    <div class="form-group">
      <label>产品类型</label>
      <div class="row">
        <select id="productType">
          <option value="web_tool">🌐 Web 工具</option>
          <option value="chrome_extension">🧩 Chrome 扩展</option>
          <option value="vscode_extension">💻 VS Code 插件</option>
          <option value="prompt_library">📝 AI 提示词包</option>
          <option value="notion_template">📋 Notion 模板</option>
        </select>
      </div>
    </div>
    <div class="form-group">
      <label>描述你的需求</label>
      <textarea id="description" placeholder="比如：一个 JSON 格式化工具，支持格式化、验证、树形查看和复制结果"></textarea>
    </div>
    <div class="form-group">
      <label>DeepSeek API Key（可选，不填则用 .env）</label>
      <input type="password" id="apiKey" placeholder="sk-..." style="font-family:monospace;font-size:12px">
    </div>
    <div class="row">
      <div class="form-group">
        <label>参赛 Agent 数</label>
        <input type="number" id="agents" value="10" min="4" max="30">
      </div>
      <div class="form-group">
        <label>进化代数</label>
        <input type="number" id="gens" value="3" min="1" max="10">
      </div>
    </div>
    <button class="btn btn-primary" id="startBtn" onclick="startArena()">
      ⚡ 开始竞技
    </button>
    <div class="error-msg" id="errorMsg" style="display:none"></div>
  </div>

  <!-- 进度卡片 -->
  <div class="card progress-panel" id="progressCard">
    <div class="card-title">
      <span class="phase-badge" id="phaseBadge">⏳ 准备中</span>
      <span style="float:right;font-size:13px;color:var(--muted)" id="timeElapsed"></span>
    </div>
    <p id="currentAction" style="font-size:14px;margin-bottom:8px">等待开始…</p>
    <div class="bar-track"><div class="bar-fill" id="barFill" style="width:0%"></div></div>
    <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted)">
      <span id="genLabel">第 1/3 代</span>
      <span id="agentLabel">Agent 0/10</span>
    </div>
    <div class="agent-list" id="agentDots"></div>
    <p id="topSoFar" style="font-size:13px;color:var(--accent2)"></p>
  </div>

  <!-- 结果卡片 -->
  <div class="card result-panel" id="resultCard">
    <div class="card-title">🏆 竞技结果</div>
    <div class="winner-card">
      <div class="winner-icon">🏆</div>
      <div class="winner-name" id="winnerName">—</div>
      <div class="winner-score" id="winnerScore">—</div>
      <div style="color:var(--muted);font-size:13px" id="winnerPath"></div>
    </div>
    <div style="margin-top:16px;display:flex;gap:12px;justify-content:center">
      <button class="btn btn-primary" id="downloadBtn" onclick="downloadWinner()">📥 下载</button>
      <button class="btn btn-primary" id="previewBtn" style="display:none;background:var(--green)" onclick="previewWinner()">👁 在线预览</button>
      <button class="btn" style="background:var(--card);border:1px solid var(--border);color:var(--text)" onclick="toggleCodePreview()">📄 看代码</button>
    </div>
    <img id="screenshotImg" src="" style="width:100%;border-radius:8px;margin-top:16px;border:1px solid var(--border);display:none" alt="生成的界面截图">
    <pre id="codePreview" style="display:none;text-align:left;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:16px;margin-top:12px;max-height:400px;overflow:auto;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-all"></pre>
    <div class="score-grid" id="scoreDetail"></div>

    <div class="card-title" style="margin-top:24px">📊 历代排名</div>
    <div id="roundsTable"></div>

    <div style="margin-top:20px;text-align:center">
      <button class="btn btn-primary" onclick="resetUI()">🔄 再来一场</button>
    </div>
  </div>
</div>

<script>
const BASE = '';

let pollingTimer = null;
let startTime = 0;
let currentWinnerPath = '';

function startArena() {
  const desc = document.getElementById('description').value.trim();
  if (!desc) {
    showError('请填写需求描述');
    return;
  }
  hideError();

  const btn = document.getElementById('startBtn');
  btn.disabled = true;
  btn.textContent = '⏳ 启动中…';

  fetch(BASE + '/api/arena/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      description: desc,
      product_type: document.getElementById('productType').value,
      agents: parseInt(document.getElementById('agents').value) || 10,
      gens: parseInt(document.getElementById('gens').value) || 3,
      api_key: document.getElementById('apiKey').value.trim(),
    }),
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) { showError(data.error); btn.disabled = false; btn.textContent = '⚡ 开始竞技'; return; }
    document.getElementById('inputCard').style.display = 'none';
    document.getElementById('progressCard').classList.add('active');
    startTime = Date.now();
    pollProgress(data.task_id);
  })
  .catch(e => { showError('启动失败: ' + e.message); btn.disabled = false; btn.textContent = '⚡ 开始竞技'; });
}

function pollProgress(taskId) {
  fetch(BASE + '/api/arena/progress/' + taskId)
    .then(r => r.json())
    .then(data => {
      const p = data.progress || data;
      const result = data.result;

      if (result) {
        showResult(result, data);
        return;
      }

      updateProgressUI(p);
      pollingTimer = setTimeout(() => pollProgress(taskId), 1000);
    })
    .catch(() => {
      pollingTimer = setTimeout(() => pollProgress(taskId), 2000);
    });
}

function updateProgressUI(p) {
  const badge = document.getElementById('phaseBadge');
  badge.textContent = {parsing:'🔍 解析意图',building:'🔨 生成代码',judging:'⚖️ 评审中',evolving:'🧬 进化中',done:'✅ 完成',idle:'⏳ 准备中'}[p.phase] || p.phase;
  badge.className = 'phase-badge phase-' + p.phase;

  document.getElementById('currentAction').textContent = p.current_action || '';
  document.getElementById('genLabel').textContent = '第 ' + (p.generation||1) + '/' + (p.total_generations||3) + ' 代';
  document.getElementById('agentLabel').textContent = 'Agent ' + (p.agents_completed||0) + '/' + (p.total_agents||10);

  const pct = p.total_agents > 0 ? Math.round((p.agents_completed||0) / p.total_agents * 100) : 0;
  document.getElementById('barFill').style.width = pct + '%';

  if (p.top_so_far) {
    document.getElementById('topSoFar').textContent = '🥇 当前领先: ' + p.top_so_far + ' (' + (p.top_score_so_far||0) + '分)';
  }

  const elapsed = Math.round((Date.now() - startTime) / 1000);
  document.getElementById('timeElapsed').textContent = elapsed + 's';

  // Agent dots
  const dots = document.getElementById('agentDots');
  dots.innerHTML = '';
  for (let i = 0; i < (p.total_agents||10); i++) {
    const d = document.createElement('span');
    d.className = 'agent-dot';
    if (i < (p.agents_completed||0)) d.classList.add('done');
    if (i === (p.agents_completed||0) && p.phase !== 'done') d.classList.add('current');
    dots.appendChild(d);
  }
}

function showResult(result, rawData) {
  clearTimeout(pollingTimer);
  document.getElementById('progressCard').classList.remove('active');
  document.getElementById('resultCard').classList.add('active');

  const w = result.winner_name || '—';
  const ws = result.winner_score || 0;
  document.getElementById('winnerName').textContent = w;
  document.getElementById('winnerScore').textContent = ws + ' 分';
  document.getElementById('winnerPath').textContent = result.winner_code_path || '';

  // Download + preview buttons
  const codePath = result.winner_code_path || '';
  const ssPath = (rounds[0]?.scores?.[0]?.screenshot_path) || '';
  if (codePath) {
    currentWinnerPath = codePath.split('/').pop();
    document.getElementById('downloadBtn').style.display = '';
    const previewable = (result.task?.product_type || '').includes('web') || (result.task?.product_type || '').includes('extension');
    document.getElementById('previewBtn').style.display = previewable ? '' : 'none';
  } else {
    currentWinnerPath = '';
    document.getElementById('downloadBtn').style.display = 'none';
    document.getElementById('previewBtn').style.display = 'none';
  }
  // Screenshot
  const ssImg = document.getElementById('screenshotImg');
  if (ssPath) {
    ssImg.src = '/screenshots/' + ssPath.split('/').pop();
    ssImg.style.display = '';
  } else {
    ssImg.style.display = 'none';
  }

  // 取第一轮中冠军的详细分数
  const rounds = result.rounds || [];
  let champDetail = null;
  if (rounds.length && rounds[0].scores) {
    champDetail = rounds[0].scores.find(s => s.agent_name === w) || rounds[0].scores[0];
  }

  if (champDetail) {
    document.getElementById('scoreDetail').innerHTML = [
      ['completeness','完整度', champDetail.completeness||0],
      ['functionality','功能', champDetail.functionality||0],
      ['code_quality','代码质量', champDetail.code_quality||0],
      ['design','设计', champDetail.design||0],
    ].map(([_,label,val]) =>
      '<div class="score-item"><div class="score-val" style="color:var(--accent2)">'+val+'</div><div class="score-label">'+label+'</div></div>'
    ).join('');
  }

  // 历代排名表
  let tableHtml = '<table class="rank-table"><tr><th></th><th>代数</th><th>冠军</th><th>分数</th><th>存活/淘汰</th></tr>';
  (rounds||[]).forEach(r => {
    const best = (r.scores||[])[0] || {};
    tableHtml += '<tr><td class="medal">'+(['🥇','🥈','🥉'][r.generation-1]||r.generation)+'</td>'
      + '<td>第'+r.generation+'代</td>'
      + '<td>'+best.agent_name+'</td>'
      + '<td style="font-weight:700;color:var(--green)">'+best.overall+'</td>'
      + '<td style="font-size:11px;color:var(--muted)">存活 '+(r.survivors||[]).length+' / 淘汰 '+((r.eliminated||[]).length)+'</td></tr>';
  });
  tableHtml += '</table>';
  document.getElementById('roundsTable').innerHTML = tableHtml;
}

function resetUI() {
  clearTimeout(pollingTimer);
  document.getElementById('resultCard').classList.remove('active');
  document.getElementById('progressCard').classList.remove('active');
  document.getElementById('inputCard').style.display = '';
  document.getElementById('startBtn').disabled = false;
  document.getElementById('startBtn').textContent = '⚡ 开始竞技';
  document.getElementById('codePreview').style.display = 'none';
  document.getElementById('downloadBtn').style.display = 'none';
  currentWinnerPath = '';
  hideError();
}

function downloadWinner(fname) {
  fname = fname || currentWinnerPath;
  if (!fname) return;
  window.open('/api/builds/' + fname, '_blank');
}

function previewWinner(fname) {
  fname = fname || currentWinnerPath;
  if (!fname) return;
  window.open('/preview/' + fname, '_blank');
}

function toggleCodePreview() {
  const pre = document.getElementById('codePreview');
  if (pre.style.display === 'none' || !pre.style.display) {
    pre.style.display = 'block';
    pre.textContent = 'Loading...';
    const fname = currentWinnerPath;
    if (!fname) { pre.textContent = '无代码包'; return; }
    fetch('/api/builds/' + fname)
      .then(r => {
        if (!r.ok) throw new Error('fail');
        return r.arrayBuffer();
      })
      .then(buf => {
        // Read zip contents via JSZip-like approach: just show zip structure
        const bytes = new Uint8Array(buf);
        let names = [];
        let pos = 0;
        while (pos < bytes.length - 30) {
          const sig = (bytes[pos] | (bytes[pos+1]<<8) | (bytes[pos+2]<<16) | (bytes[pos+3]<<24)) >>> 0;
          if (sig === 0x04034b50) {
            const nameLen = bytes[pos+26] | (bytes[pos+27]<<8);
            const extraLen = bytes[pos+28] | (bytes[pos+29]<<8);
            let name = '';
            for (let i = 0; i < nameLen; i++) name += String.fromCharCode(bytes[pos+30+i]);
            const compSize = bytes[pos+18] | (bytes[pos+19]<<8) | (bytes[pos+20]<<16) | (bytes[pos+21]<<24);
            const dataStart = pos + 30 + nameLen + extraLen;
            let content = '';
            for (let i = 0; i < Math.min(compSize, 3000); i++) {
              content += String.fromCharCode(bytes[dataStart + i]);
            }
            let ext = name.split('.').pop();
            names.push({name, content, ext, size: compSize});
            pos = dataStart + compSize;
          } else { pos++; }
        }
        let out = '';
        names.forEach(f => {
          out += '\n══════ ' + f.name + ' (' + f.size + ' bytes) ══════\n';
          out += f.content;
          if (f.size > 3000) out += '\n... (truncated)';
          out += '\n';
        });
        pre.textContent = out || '(empty zip)';
      })
      .catch(e => { pre.textContent = '加载失败: ' + e.message; });
  } else {
    pre.style.display = 'none';
  }
}

function showError(msg) {
  const el = document.getElementById('errorMsg');
  el.textContent = msg;
  el.style.display = '';
}
function hideError() { document.getElementById('errorMsg').style.display = 'none'; }
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AlphaX Arena Web Server")
    parser.add_argument("--port", type=int, default=8899)
    args = parser.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), ArenaHandler)
    print(f"🧬 AlphaX Arena")
    print(f"   打开浏览器 → http://localhost:{args.port}")
    print(f"   按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 关闭")
        server.server_close()


if __name__ == "__main__":
    main()
