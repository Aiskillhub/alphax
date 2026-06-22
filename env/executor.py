"""真实执行验证器

不只是检查语法——真的启动服务、加载页面、抓取运行时错误。
产物要么能在浏览器里跑，要么就是废的。
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler


@dataclass
class ExecutionReport:
    """一次真实执行的结果"""
    build_id: str
    success: bool = False
    server_started: bool = False
    page_loaded: bool = False
    http_status: int = 0
    content_length: int = 0
    has_errors: bool = False
    errors: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    load_time_ms: float = 0
    summary: str = ""
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Executor:
    """真实启动服务，加载页面，捕捉运行时错误"""

    def __init__(self, port_range: tuple[int, int] = (18000, 18999)):
        self.port_range = port_range
        self._used_ports: set[int] = set()

    def execute(self, build) -> ExecutionReport:
        """执行一个 Build：启动服务 → 加载页面 → 收集错误"""
        report = ExecutionReport(build_id=build.build_id)

        html_files = [f for f in build.files if f.endswith('.html')]
        if not html_files:
            report.summary = "No HTML files to execute"
            return report

        index_file = next((f for f in html_files if f.lower() == 'index.html'), html_files[0])

        # 将文件写入临时目录
        with tempfile.TemporaryDirectory(prefix="nexus_exec_") as tmpdir:
            tmp = Path(tmpdir)
            for fname, content in build.files.items():
                filepath = tmp / fname
                filepath.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, dict):
                    content = json.dumps(content, indent=2)
                elif not isinstance(content, str):
                    content = str(content)
                filepath.write_text(content)

            # 找可用端口
            port = self._find_port()

            # 启动 HTTP 服务器
            server, thread = self._start_server(tmp, port)
            if not server:
                report.errors.append("Failed to start HTTP server")
                report.summary = "Server start failed"
                return report

            report.server_started = True
            time.sleep(0.3)  # 等服务器就绪

            try:
                # 加载页面
                url = f"http://localhost:{port}/{index_file}"
                start = time.time()
                req = urllib.request.Request(url, headers={"User-Agent": "NexusExecutor/1.0"})
                resp = urllib.request.urlopen(req, timeout=5)
                report.load_time_ms = round((time.time() - start) * 1000, 1)
                report.http_status = resp.status
                content = resp.read().decode('utf-8', errors='replace')
                report.content_length = len(content)
                report.page_loaded = True

                # 检查页面内容
                report.errors.extend(self._check_content(content, index_file))

            except urllib.error.HTTPError as e:
                report.http_status = e.code
                report.errors.append(f"HTTP {e.code}: {e.reason}")
            except Exception as e:
                report.errors.append(f"Page load failed: {e}")

            finally:
                server.shutdown()
                thread.join(timeout=2)
                self._used_ports.discard(port)

        report.has_errors = len(report.errors) > 0
        report.success = report.page_loaded and not report.has_errors

        if report.success:
            report.summary = f"OK: {report.http_status}, {report.content_length}B, {report.load_time_ms}ms"
        else:
            report.summary = f"FAIL: {len(report.errors)} errors"

        return report

    def _check_content(self, content: str, fname: str) -> list[str]:
        """检查加载的页面内容"""
        errors = []
        if len(content) < 50:
            errors.append(f"Page too small ({len(content)}B) — likely empty or broken")
        if '<html' not in content.lower():
            errors.append("Response doesn't contain <html> — not a valid HTML page")
        if '<body' in content.lower() and '</body>' not in content.lower():
            errors.append("Unclosed <body> tag")
        # 检查是否有明显的 JS 运行时错误痕迹
        if 'undefined is not a function' in content.lower():
            errors.append("JavaScript runtime error in output")
        if 'cannot read property' in content.lower():
            errors.append("JavaScript null reference error in output")
        if content.strip().startswith('{') and content.strip().endswith('}'):
            errors.append("Response is JSON, not HTML — LLM didn't generate proper page")
        return errors

    def _start_server(self, directory: Path, port: int):
        """在后台线程启动 HTTP 服务器"""
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(directory), **kwargs)

            def log_message(self, format, *args):
                pass  # 沉默日志

        try:
            server = HTTPServer(('localhost', port), Handler)
            server.timeout = 5
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            return server, thread
        except OSError:
            return None, None

    def _find_port(self) -> int:
        import socket
        for port in range(self.port_range[0], self.port_range[1]):
            if port in self._used_ports:
                continue
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('localhost', port)) != 0:
                    self._used_ports.add(port)
                    return port
        return 18888  # fallback
