"""产品封面自动生成

为每个产品生成精美的 SVG 封面图 → 转 PNG → 上传 Gumroad。
不用手动做图，产品名+品类+价格自动变视觉。
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class CoverResult:
    """一个封面生成结果"""
    product_id: str
    svg_path: str = ""
    png_path: str = ""
    uploaded: bool = False
    error: str = ""


class ScreenshotGenerator:
    """从产品元数据生成专业封面图"""

    # 配色方案池
    PALETTES = [
        {"bg": "#0f0f1b", "accent1": "#7c3aed", "accent2": "#06b6d4", "text": "#f8fafc"},
        {"bg": "#0c0a09", "accent1": "#f97316", "accent2": "#eab308", "text": "#fafaf9"},
        {"bg": "#022c22", "accent1": "#10b981", "accent2": "#34d399", "text": "#ecfdf5"},
        {"bg": "#1e1b4b", "accent1": "#818cf8", "accent2": "#c084fc", "text": "#eef2ff"},
        {"bg": "#1a0a1e", "accent1": "#d946ef", "accent2": "#f472b6", "text": "#fdf4ff"},
        {"bg": "#0f172a", "accent1": "#3b82f6", "accent2": "#06b6d4", "text": "#f0f9ff"},
    ]

    def __init__(self):
        self._token = config.gumroad_access_token
        self._cache_path = config.data_dir / "covers.json"
        self._history: dict[str, CoverResult] = {}
        self._load()

    def generate(self, organism, build) -> CoverResult | None:
        """为一个产品生成封面图"""
        genome = organism.genome
        if not genome:
            return None

        pid = getattr(organism, 'gumroad_product_id', '') or organism.organism_id
        name = str(genome.express() if hasattr(genome, 'express') else f"AI Tool")
        category = str(getattr(genome, 'category', 'Dev Tools'))
        price = getattr(genome, 'price_point', 4.99)

        try:
            palette = self.PALETTES[hash(category) % len(self.PALETTES)]
            svg = self._render_svg(name, category, price, palette)

            svg_path = config.data_dir / f"cover_{pid[:12]}.svg"
            svg_path.write_text(svg)

            # 转 PNG
            png_path = config.data_dir / f"cover_{pid[:12]}.png"
            self._svg_to_png(svg_path, png_path)

            result = CoverResult(
                product_id=pid,
                svg_path=str(svg_path),
                png_path=str(png_path),
            )

            # 如果有 Gumroad product ID，尝试上传缩略图
            if pid and self._token:
                result.uploaded = self._upload_thumbnail(pid, png_path)

            self._history[pid] = result
            self._save()
            return result

        except Exception as e:
            return CoverResult(product_id=pid, error=str(e))

    def _render_svg(self, name: str, category: str, price: float, palette: dict) -> str:
        """生成 SVG 封面"""
        name_short = name[:40]
        price_str = f"${price:.2f}" if price >= 1 else f"{int(price * 100)}¢"

        return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{palette['bg']}"/>
      <stop offset="100%" style="stop-color:{palette['bg']}dd"/>
    </linearGradient>
    <linearGradient id="accent" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{palette['accent1']}"/>
      <stop offset="100%" style="stop-color:{palette['accent2']}"/>
    </linearGradient>
  </defs>

  <rect width="800" height="500" rx="24" fill="url(#bg)"/>

  <!-- 装饰圆 -->
  <circle cx="650" cy="120" r="180" fill="{palette['accent1']}" opacity="0.08"/>
  <circle cx="120" cy="400" r="120" fill="{palette['accent2']}" opacity="0.06"/>

  <!-- 品类标签 -->
  <rect x="40" y="40" rx="12" width="160" height="32" fill="{palette['accent1']}" opacity="0.2"/>
  <text x="120" y="62" font-family="system-ui, sans-serif" font-size="15" fill="{palette['accent2']}" text-anchor="middle" font-weight="600">{category[:16]}</text>

  <!-- 产品名 -->
  <text x="40" y="180" font-family="system-ui, sans-serif" font-size="38" fill="{palette['text']}" font-weight="700" letter-spacing="-0.5">
    {self._wrap_text(name_short, 28)[0] if self._wrap_text(name_short, 28) else name_short}
  </text>
  {self._render_subtitle(name_short, palette)}

  <!-- 价格 -->
  <rect x="40" y="380" rx="16" width="140" height="52" fill="url(#accent)"/>
  <text x="110" y="414" font-family="system-ui, sans-serif" font-size="28" fill="#fff" text-anchor="middle" font-weight="800">{price_str}</text>

  <!-- one-time 标记 -->
  <text x="200" y="414" font-family="system-ui, sans-serif" font-size="15" fill="{palette['text']}" opacity="0.5">one-time</text>

  <!-- footer -->
  <text x="40" y="470" font-family="system-ui, sans-serif" font-size="12" fill="{palette['text']}" opacity="0.25">Alpha X</text>
</svg>'''

    def _render_subtitle(self, name: str, palette: dict) -> str:
        lines = self._wrap_text(name, 28)
        if len(lines) > 1:
            return f'<text x="40" y="230" font-family="system-ui, sans-serif" font-size="20" fill="{palette["text"]}" opacity="0.6">{lines[1]}</text>'
        return ""

    @staticmethod
    def _wrap_text(text: str, max_chars: int) -> list[str]:
        if len(text) <= max_chars:
            return [text]
        words = text.split()
        lines = []
        current = ""
        for word in words:
            if len(current) + len(word) + 1 <= max_chars:
                current = f"{current} {word}".strip()
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines[:2]

    def _svg_to_png(self, svg_path: Path, png_path: Path) -> bool:
        """SVG 转 PNG"""
        try:
            result = subprocess.run(
                ["qlmanage", "-t", "-s", "800", "-o", str(png_path.parent), str(svg_path)],
                capture_output=True, timeout=15,
            )
            if result.returncode == 0:
                # qlmanage 输出为 svg_path.png
                generated = Path(str(svg_path) + ".png")
                if generated.exists():
                    generated.rename(png_path)
                    return True

            # fallback: 尝试 rsvg-convert
            result2 = subprocess.run(
                ["rsvg-convert", "-w", "800", "-o", str(png_path), str(svg_path)],
                capture_output=True, timeout=15,
            )
            return result2.returncode == 0
        except Exception:
            return False

    def _upload_thumbnail(self, product_id: str, png_path: Path) -> bool:
        """上传封面到 Gumroad 作为产品缩略图"""
        if not self._token or not png_path.exists():
            return False

        try:
            boundary = "----FormBoundary7MA4YWxkTrZu0gW"
            with open(png_path, "rb") as f:
                file_data = f.read()

            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{png_path.name}"\r\n'
                f"Content-Type: image/png\r\n\r\n"
            ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

            req = urllib.request.Request(
                f"https://api.gumroad.com/v2/products/{product_id}",
                data=body,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate_for_existing(self, product_id: str, name: str, category: str = "Dev Tools", price: float = 4.99) -> CoverResult | None:
        """为已存在的产品生成封面"""
        palette = self.PALETTES[hash(category) % len(self.PALETTES)]
        svg = self._render_svg(name, category, price, palette)

        svg_path = config.data_dir / f"cover_{product_id[:12]}.svg"
        svg_path.write_text(svg)

        png_path = config.data_dir / f"cover_{product_id[:12]}.png"
        ok = self._svg_to_png(svg_path, png_path)

        result = CoverResult(
            product_id=product_id,
            svg_path=str(svg_path),
            png_path=str(png_path) if ok else "",
        )

        if ok and self._token:
            result.uploaded = self._upload_thumbnail(product_id, png_path)

        self._history[product_id] = result
        self._save()
        return result

    @property
    def summary(self) -> dict:
        return {
            "covers_generated": len(self._history),
            "uploaded": sum(1 for r in self._history.values() if r.uploaded),
        }

    def _save(self):
        try:
            data = {
                pid: {
                    "product_id": r.product_id, "svg_path": r.svg_path,
                    "png_path": r.png_path, "uploaded": r.uploaded, "error": r.error,
                }
                for pid, r in self._history.items()
            }
            self._cache_path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _load(self):
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text())
                for pid, d in data.items():
                    self._history[pid] = CoverResult(**d)
            except (json.JSONDecodeError, OSError):
                pass
