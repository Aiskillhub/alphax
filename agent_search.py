"""AlphaX Agent Reach — 联网搜索能力层

给 AlphaX Agent 装上眼睛：生成代码前先搜竞品、参考实现。
底层复用 Agent-Reach 安装的 CLI 工具（gh/yt-dlp/Jina Reader）。

用法：
  from agent_search import AgentSearcher
  searcher = AgentSearcher()
  refs = searcher.research_context("番茄钟工具")
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path


class AgentSearcher:
    """AlphaX Agent 联网搜索器 — 调用底层 CLI 工具获取外部参考。"""

    def __init__(self, timeout: int = 20):
        self._timeout = timeout

    @property
    def is_available(self) -> bool:
        """检查至少有一个可用搜索渠道。"""
        return any([
            self._cmd_exists("gh"),
            self._cmd_exists("yt-dlp"),
            True,  # Jina Reader 无需客户端
        ])

    def research_context(self, query: str, sources: list[str] | None = None,
                         max_results: int = 3) -> str:
        """返回可拼入 LLM prompt 的参考上下文文本。

        Args:
            query: 搜索关键词
            sources: 要搜的来源，默认 ['web', 'github']
            max_results: 每源最大结果数

        Returns:
            格式化的参考文本，可直接拼入 LLM prompt
        """
        sources = sources or ["web", "github"]
        lines = ["\n## 🔍 联网参考（Agent-Reach）\n"]

        for src in sources:
            handler = getattr(self, f"_search_{src}", None)
            if not handler:
                continue
            try:
                results = handler(query, max_results)
                if results:
                    lines.append(f"### {src.upper()} 搜索结果:\n")
                    for item in results[:max_results]:
                        title = item.get("title", "")
                        snippet = item.get("snippet", "")[:200]
                        url = item.get("url", "")
                        if title:
                            lines.append(f"- **{title}**")
                        if snippet:
                            lines.append(f"  {snippet}")
                        if url:
                            lines.append(f"  {url}")
                        lines.append("")
            except Exception as e:
                continue

        return "\n".join(lines) if len(lines) > 1 else ""

    # ── 各平台搜索 ──

    def _search_web(self, query: str, n: int) -> list[dict]:
        """通过 Exa 搜索（mcporter，免费无 key）。"""
        try:
            result = subprocess.run(
                ["mcporter", "call", "exa.web_search_exa",
                 f"query={query}", f"num_results={n}"],
                capture_output=True, text=True, timeout=self._timeout,
            )
            if result.returncode != 0:
                return self._web_jina(query, n)
            return self._parse_exa_output(result.stdout, n)
        except Exception:
            return self._web_jina(query, n)

    def _parse_exa_output(self, raw: str, n: int) -> list[dict]:
        """解析 Exa 搜索结果。"""
        items = []
        current = {}
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line:
                if current:
                    items.append(current)
                    current = {}
                continue
            if line.startswith("Title: "):
                current["title"] = line[7:]
            elif line.startswith("URL: "):
                current["url"] = line[5:]
            elif line.startswith("Highlights:"):
                pass  # 下一行开始是内容
            elif line and not line.startswith("..."):
                current["snippet"] = line[:300]
        if current:
            items.append(current)
        return [i for i in items if i.get("title") or i.get("snippet")][:n]

    def _web_jina(self, query: str, n: int) -> list[dict]:
        """Jina Reader 降级方案 — 直接读文本。"""
        encoded = urllib.parse.quote(query)
        url = f"https://r.jina.ai/https://www.google.com/search?q={encoded}"
        try:
            req = urllib.request.Request(
                url,
                headers={"X-Return-Format": "text"},
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            lines = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith("[")][:n]
            return [{"title": "", "snippet": l[:200], "url": ""} for l in lines]
        except Exception:
            return []

    def _search_github(self, query: str, n: int) -> list[dict]:
        """通过 gh CLI 搜索 GitHub 仓库。"""
        if not self._cmd_exists("gh"):
            return self._github_web(query, n)

        try:
            result = subprocess.run(
                ["gh", "search", "repos", query, "--sort", "stars", "--limit", str(n),
                 "--json", "nameWithOwner,description,url,stargazersCount"],
                capture_output=True, text=True, timeout=self._timeout,
            )
            if result.returncode != 0:
                return self._github_web(query, n)
            data = json.loads(result.stdout)
            items = [
                {
                    "title": f"{item['nameWithOwner']} (⭐{item.get('stargazersCount', 0)})",
                    "snippet": item.get("description", "")[:200],
                    "url": item.get("url", ""),
                }
                for item in data[:n]
            ]
            return items if items else self._github_web(query, n)
        except Exception:
            return self._github_web(query, n)

    def _github_web(self, query: str, n: int) -> list[dict]:
        """GitHub 网页搜索 fallback。"""
        return self._search_web(f"site:github.com {query}", n)

    def _search_youtube(self, query: str, n: int) -> list[dict]:
        """通过 yt-dlp 搜索 YouTube。"""
        if not self._cmd_exists("yt-dlp"):
            return []

        try:
            result = subprocess.run(
                ["yt-dlp", f"ytsearch{n}:{query}", "--dump-json", "--skip-download",
                 "--no-warnings"],
                capture_output=True, text=True, timeout=self._timeout,
            )
            items = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                try:
                    v = json.loads(line)
                    items.append({
                        "title": v.get("title", ""),
                        "snippet": v.get("description", "")[:200],
                        "url": v.get("webpage_url", ""),
                    })
                except json.JSONDecodeError:
                    continue
            return items[:n]
        except Exception:
            return []

    # ── 工具 ──

    @staticmethod
    def _cmd_exists(cmd: str) -> bool:
        """检查命令是否可用。"""
        try:
            subprocess.run(
                ["which", cmd], capture_output=True, timeout=5,
            )
            return True
        except Exception:
            return False
