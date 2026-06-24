"""AlphaX Arena — 截图工具

为生成的 Web 工具自动截图，让裁判看图评审。
依赖：playwright（pip install playwright && playwright install chromium）
"""

from __future__ import annotations

from pathlib import Path


def capture_web_tool(html_path: Path, output_path: Path):
    """对 Web 工具 HTML 截图，返回截图路径。失败返回 None。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(f"file://{html_path.absolute()}")
            page.wait_for_timeout(500)  # 等渲染
            page.screenshot(path=str(output_path), full_page=False)
            browser.close()
        return output_path
    except Exception:
        return None


def capture_zip(zip_path):
    """解压 zip 包，对其中 HTML 截图。"""
    """解压 zip 包，对其中 HTML 截图。"""
    import tempfile
    import zipfile

    zip_path = Path(zip_path)
    if not zip_path.exists():
        return None

    try:
        with zipfile.ZipFile(zip_path) as zf:
            html_name = None
            for name in zf.namelist():
                if name.endswith(".html"):
                    html_name = name
                    break
            if not html_name:
                return None

            with tempfile.TemporaryDirectory() as tmp:
                zf.extract(html_name, tmp)
                html_file = Path(tmp) / html_name
                screenshot_path = zip_path.parent / f"{zip_path.stem}_screenshot.png"
                return capture_web_tool(html_file, screenshot_path)
    except Exception:
        return None
