"""AlphaX Builder — Chrome Extension 生成器

根据基因组自动生成完整的 Chrome Extension 代码。
每个基因组映射为一组可组合的代码模块。
"""

from __future__ import annotations

import json
import shutil
import struct
import tempfile
import zipfile
import zlib
from pathlib import Path

from core.genome import Genome, Category, TargetMarket
from config import config


class ExtensionBuilder:
    """根据基因组生成 Chrome Extension"""

    _build_dir: Path = config.data_dir / "builds"

    def build(self, genome: Genome, organism_id: str) -> Path:
        """生成完整扩展包，返回 zip 文件路径"""
        self._build_dir.mkdir(parents=True, exist_ok=True)
        work_dir = self._build_dir / organism_id
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir()

        manifest = self._generate_manifest(genome)
        content = self._generate_content_script(genome)
        popup_html = self._generate_popup_html(genome)
        popup_js = self._generate_popup_js(genome)
        background = self._generate_background(genome)

        (work_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        (work_dir / "content.js").write_text(content)
        (work_dir / "popup.html").write_text(popup_html)
        (work_dir / "popup.js").write_text(popup_js)
        (work_dir / "background.js").write_text(background)

        self._generate_icon(work_dir / "icon48.png", 48, genome)
        self._generate_icon(work_dir / "icon128.png", 128, genome)

        zip_path = self._build_dir / f"{organism_id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in work_dir.iterdir():
                zf.write(f, f.name)

        return zip_path

    def _generate_icon(self, path: Path, size: int, genome: Genome):
        """用纯 Python stdlib 生成有效 PNG 图标（Chrome Web Store 必需）"""
        import struct, zlib

        color = hash(genome.category.value) & 0xFFFFFF if genome else 0x6366F1
        r, g, b = (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF

        # 构建 RGBA 像素行
        raw = b""
        for y in range(size):
            raw += b"\x00"  # filter byte
            for x in range(size):
                # 白色 "A" 字形中心标记
                cx, cy = size // 2, size // 2
                in_a = (x - cx + y - cy) // 6 == 0 and abs(x - cx) < size // 4
                in_x = abs(x - y) < size // 8 or abs(x + y - size) < size // 8
                if in_a or (in_x and abs(x - cx) < size // 4):
                    raw += bytes([255, 255, 255, 255])
                else:
                    raw += bytes([r, g, b, 255])

        def _chunk(ctype, data):
            c = ctype + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        png = b"\x89PNG\r\n\x1a\n"
        png += _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        png += _chunk(b"IDAT", zlib.compress(raw))
        png += _chunk(b"IEND", b"")

        path.write_bytes(png)

    def _generate_manifest(self, genome: Genome) -> dict:
        name = genome.express()
        return {
            "manifest_version": 3,
            "name": name,
            "version": "1.0.0",
            "description": self._description(genome),
            "permissions": self._permissions(genome),
            "host_permissions": self._host_permissions(genome),
            "action": {
                "default_popup": "popup.html",
                "default_title": name,
            },
            "background": {
                "service_worker": "background.js",
            },
            "content_scripts": [{
                "matches": self._content_matches(genome),
                "js": ["content.js"],
            }],
            "icons": {
                "48": "icon48.png",
                "128": "icon128.png",
            },
        }

    def _generate_content_script(self, genome: Genome) -> str:
        if genome.category == Category.AI_CHAT:
            return self._ai_chat_content(genome)
        elif genome.category == Category.PRODUCTIVITY:
            return self._productivity_content(genome)
        elif genome.category == Category.DEV_TOOLS:
            return self._devtools_content(genome)
        else:
            return self._generic_content(genome)

    def _ai_chat_content(self, genome: Genome) -> str:
        return """// AlphaX Generated — AI Chat Enhancement
(function() {
  'use strict';

  // Detect which AI platform we're on
  const platform = (() => {
    if (location.hostname.includes('chatgpt.com')) return 'chatgpt';
    if (location.hostname.includes('claude.ai')) return 'claude';
    if (location.hostname.includes('chat.deepseek.com')) return 'deepseek';
    return 'unknown';
  })();

  // Conversation export functionality
  function extractConversation() {
    const selectors = {
      chatgpt: '[data-message-author-role]',
      claude: '.font-claude-message',
      deepseek: '.ds-markdown',
    };
    const sel = selectors[platform];
    if (!sel) return [];

    const messages = [];
    document.querySelectorAll(sel).forEach((el, i) => {
      const role = el.getAttribute('data-message-author-role') ||
                   (el.closest('.human') ? 'user' : 'assistant');
      messages.push({ index: i, role: role, content: el.textContent.trim() });
    });
    return messages;
  }

  function exportAsMarkdown(messages) {
    let md = '# AI Chat Export\\n\\n';
    md += `Platform: ${platform}\\n`;
    md += `Date: ${new Date().toISOString().split('T')[0]}\\n`;
    md += `Messages: ${messages.length}\\n\\n---\\n\\n`;
    messages.forEach(m => {
      md += `## ${m.role === 'user' ? 'You' : 'Assistant'}\\n\\n${m.content}\\n\\n`;
    });
    return md;
  }

  function download(content, filename, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  }

  // Listen for messages from popup
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'export') {
      const messages = extractConversation();
      if (request.format === 'markdown') {
        download(exportAsMarkdown(messages),
          `chat-export-${Date.now()}.md`, 'text/markdown');
      }
      sendResponse({ success: true, count: messages.length });
    }
    if (request.action === 'search') {
      const messages = extractConversation();
      const q = request.query.toLowerCase();
      const results = messages.filter(m => m.content.toLowerCase().includes(q));
      sendResponse({ success: true, results, count: results.length });
    }
  });

  console.log('[AlphaX] Content script loaded on', platform);
})();
"""

    def _productivity_content(self, genome: Genome) -> str:
        return """// AlphaX Generated — Productivity Enhancement
(function() {
  'use strict';
  // Task capture and organization
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'capture') {
      const sel = window.getSelection().toString();
      sendResponse({ success: true, text: sel, url: location.href, title: document.title });
    }
  });
  console.log('[AlphaX] Productivity content script loaded');
})();
"""

    def _devtools_content(self, genome: Genome) -> str:
        return """// AlphaX Generated — Developer Tools
(function() {
  'use strict';
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'inspect') {
      const info = {
        scripts: document.scripts.length,
        forms: document.forms.length,
        links: document.links.length,
        tech: (() => {
          const h = document.documentElement.innerHTML;
          const tech = [];
          if (h.includes('__NEXT_DATA__')) tech.push('Next.js');
          if (h.includes('_next/static')) tech.push('Next.js');
          if (document.querySelector('[data-reactroot]')) tech.push('React');
          if (document.querySelector('#__nuxt')) tech.push('Nuxt');
          if (document.querySelector('[ng-version]')) tech.push('Angular');
          return tech.length ? tech : ['Unknown'];
        })(),
      };
      sendResponse({ success: true, info });
    }
  });
  console.log('[AlphaX] DevTools content script loaded');
})();
"""

    def _generic_content(self, genome: Genome) -> str:
        return """// AlphaX Generated — Generic Content Script
(function() {
  'use strict';
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    sendResponse({ success: true });
  });
})();
"""

    def _generate_popup_html(self, genome: Genome) -> str:
        name = genome.express()
        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{name}</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ width: 320px; font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 14px; padding: 16px; }}
    h1 {{ font-size: 16px; margin-bottom: 12px; color: #1a1a1a; }}
    .btn {{ display: block; width: 100%; padding: 10px; margin: 6px 0; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; }}
    .btn-primary {{ background: #2563eb; color: white; }}
    .btn-primary:hover {{ background: #1d4ed8; }}
    .btn-secondary {{ background: #f3f4f6; color: #374151; }}
    .btn-secondary:hover {{ background: #e5e7eb; }}
    .search-box {{ width: 100%; padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; margin-bottom: 8px; }}
    .status {{ margin-top: 12px; padding: 8px; border-radius: 6px; font-size: 12px; text-align: center; display: none; }}
    .status.success {{ background: #dcfce7; color: #166534; display: block; }}
    .status.error {{ background: #fef2f2; color: #991b1b; display: block; }}
    #results {{ max-height: 200px; overflow-y: auto; margin-top: 8px; font-size: 12px; }}
    .result-item {{ padding: 6px 8px; border-bottom: 1px solid #f3f4f6; cursor: pointer; }}
    .result-item:hover {{ background: #f9fafb; }}
  </style>
</head>
<body>
  <h1>{name}</h1>
  <button id="btn-export-md" class="btn btn-primary">Export as Markdown</button>
  <button id="btn-export-txt" class="btn btn-secondary">Export as Text</button>
  <hr style="margin: 12px 0; border: none; border-top: 1px solid #e5e7eb;">
  <input type="text" id="search-input" class="search-box" placeholder="Search conversations...">
  <button id="btn-search" class="btn btn-secondary">Search</button>
  <div id="results"></div>
  <div id="status" class="status"></div>
  <script src="popup.js"></script>
</body>
</html>
"""

    def _generate_popup_js(self, genome: Genome) -> str:
        return """const status = (msg, type) => {
  const el = document.getElementById('status');
  el.textContent = msg; el.className = `status ${type}`;
  setTimeout(() => el.className = 'status', 3000);
};

const send = (action, data = {}) => {
  return new Promise(resolve => {
    chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
      chrome.tabs.sendMessage(tabs[0].id, { action, ...data }, resolve);
    });
  });
};

document.getElementById('btn-export-md').addEventListener('click', async () => {
  const res = await send('export', { format: 'markdown' });
  if (res?.success) status(`Exported ${res.count} messages`, 'success');
  else status('Export failed', 'error');
});

document.getElementById('btn-export-txt').addEventListener('click', async () => {
  const res = await send('export', { format: 'text' });
  if (res?.success) status(`Exported ${res.count} messages`, 'success');
  else status('Export failed', 'error');
});

document.getElementById('btn-search').addEventListener('click', async () => {
  const q = document.getElementById('search-input').value.trim();
  if (!q) return;
  const res = await send('search', { query: q });
  const resultsEl = document.getElementById('results');
  if (res?.success && res.results.length > 0) {
    resultsEl.innerHTML = res.results.map(r =>
      `<div class="result-item">${r.content.substring(0, 80)}...</div>`
    ).join('');
    status(`Found ${res.count} results`, 'success');
  } else {
    resultsEl.innerHTML = '<div style="padding:8px;color:#6b7280;">No results</div>';
    status('No results found', 'error');
  }
});
"""

    def _generate_background(self, genome: Genome) -> str:
        return """// AlphaX Background Service Worker
chrome.runtime.onInstalled.addListener(() => {
  console.log('[AlphaX] Extension installed');
});

chrome.action.onClicked.addListener((tab) => {
  console.log('[AlphaX] Extension clicked on', tab.url);
});
"""

    def _description(self, genome: Genome) -> str:
        return (
            f"{genome.benefit}. "
            f"{'One-click operation. ' if 'One-Click' in genome.title_pattern.value else ''}"
            f"Supports exporting conversations to Markdown and text formats."
        )

    def _permissions(self, genome: Genome) -> list[str]:
        base = ["activeTab", "scripting", "storage"]
        if genome.category == Category.AI_CHAT:
            base.append("downloads")
        return base

    def _host_permissions(self, genome: Genome) -> list[str]:
        if genome.category == Category.AI_CHAT:
            return [
                "https://chatgpt.com/*",
                "https://claude.ai/*",
                "https://chat.deepseek.com/*",
            ]
        return ["<all_urls>"]

    def _content_matches(self, genome: Genome) -> list[str]:
        return self._host_permissions(genome)
