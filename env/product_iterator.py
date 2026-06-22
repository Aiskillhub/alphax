"""产品自我迭代引擎

部署后不是放着不管——销量差的自动改进。
每 3 天检查一遍，0 销量的产品用 LLM 重新优化标题/描述。
"""

from __future__ import annotations

import json
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class IterationRecord:
    """一次迭代记录"""
    product_id: str
    iteration: int
    old_title: str
    new_title: str
    old_description: str
    new_description: str
    reason: str
    improved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ProductIterator:
    """自动优化表现差的产品"""

    MAX_ITERATIONS = 3
    STALE_DAYS = 3  # 上架多少天后 0 销量触发改进

    def __init__(self):
        self._token = config.gumroad_access_token
        self._api_base = "https://api.gumroad.com/v2"
        self._cache_path = config.data_dir / "product_iterations.json"
        self._history: dict[str, list[IterationRecord]] = {}
        self._load()

    def scan_and_improve(self) -> list[dict]:
        """扫描所有产品，改进表现差的。返回改进结果列表"""
        if not self._token:
            return []

        products = self._fetch_products()
        improvements = []

        for p in products:
            pid = p.get("id", "")
            sales = p.get("sales_count", 0)
            name = p.get("name", "")
            desc = p.get("description", "")

            # 跳过有销量的
            if sales > 0:
                continue

            # 检查是否需要改进
            if not self._should_improve(pid):
                continue

            iteration = len(self._history.get(pid, [])) + 1
            if iteration > self.MAX_ITERATIONS:
                continue

            # LLM 生成改进版的标题和描述
            improved = self._llm_improve(name, desc, sales, iteration)
            if not improved:
                continue

            new_title = improved.get("title", name)
            new_desc = improved.get("description", desc)

            # 更新 Gumroad
            if self._update_product(pid, new_title, new_desc):
                record = IterationRecord(
                    product_id=pid,
                    iteration=iteration,
                    old_title=name,
                    new_title=new_title,
                    old_description=desc,
                    new_description=new_desc,
                    reason=improved.get("reason", "0 sales, auto-optimize"),
                )
                if pid not in self._history:
                    self._history[pid] = []
                self._history[pid].append(record)
                self._save()

                improvements.append({
                    "product_id": pid,
                    "iteration": iteration,
                    "old_title": name,
                    "new_title": new_title,
                })

        return improvements

    def _should_improve(self, pid: str) -> bool:
        history = self._history.get(pid, [])
        if len(history) >= self.MAX_ITERATIONS:
            return False
        # 检查上次改进是否在 STALE_DAYS 之前
        if history:
            last = history[-1]
            last_date = datetime.fromisoformat(last.improved_at.replace("Z", "+00:00"))
            days_since = (datetime.now(timezone.utc) - last_date).days
            return days_since >= self.STALE_DAYS
        return True

    def _llm_improve(self, title: str, description: str, sales: int, iteration: int) -> dict | None:
        """LLM 生成改进方案"""
        if not config.deepseek_api_key:
            return self._rule_improve(title, iteration)

        prompt = f"""You are a conversion optimization expert. A product has {sales} sales.

Current title: "{title}"
Current description: "{description}"

Iteration #{iteration}. This is the {iteration}th attempt to improve it.

Suggest a better title and description that would increase sales. Focus on:
1. Clearer value proposition
2. Better hook in first sentence
3. More specific benefits

Return JSON:
{{
  "title": "improved title (max 60 chars)",
  "description": "improved description (max 500 chars)",
  "reason": "one sentence why this should convert better"
}}

Output ONLY valid JSON."""

        try:
            body = json.dumps({
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "You optimize product listings for conversion. Output only JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.6,
                "max_tokens": 1000,
            }).encode()

            req = urllib.request.Request(
                f"{config.deepseek_base_url}/v1/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {config.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                content = data["choices"][0]["message"]["content"]
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    return json.loads(content[start:end])
        except Exception:
            pass
        return None

    def _rule_improve(self, title: str, iteration: int) -> dict | None:
        """无 LLM 时的规则改进"""
        prefixes = [
            "Instantly ", "The Ultimate ", "One-Click ", "Pro ",
        ]
        suffix = f" — v{iteration + 1}"
        new_title = prefixes[iteration % len(prefixes)] + title.split("—")[0].strip() + suffix
        return {
            "title": new_title[:60],
            "description": f"Updated version with improved performance. {new_title}",
            "reason": "auto-optimize iteration",
        }

    def _update_product(self, pid: str, title: str, description: str) -> bool:
        """通过 Gumroad API 更新产品"""
        try:
            data = urllib.parse.urlencode({
                "name": title,
                "description": description,
            }).encode()
            req = urllib.request.Request(
                f"{self._api_base}/products/{pid}",
                data=data,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _fetch_products(self) -> list[dict]:
        try:
            req = urllib.request.Request(
                f"{self._api_base}/products",
                headers={"Authorization": f"Bearer {self._token}"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read()).get("products", [])
        except Exception:
            return []

    @property
    def summary(self) -> dict:
        total_iterations = sum(len(v) for v in self._history.values())
        return {
            "products_tracked": len(self._history),
            "total_iterations": total_iterations,
            "recent": [
                {"product_id": pid, "iterations": len(recs), "latest": recs[-1].new_title[:50] if recs else ""}
                for pid, recs in list(self._history.items())[-5:]
            ],
        }

    def _save(self):
        try:
            data = {
                pid: [
                    {
                        "product_id": r.product_id, "iteration": r.iteration,
                        "old_title": r.old_title, "new_title": r.new_title,
                        "old_description": r.old_description, "new_description": r.new_description,
                        "reason": r.reason, "improved_at": r.improved_at,
                    }
                    for r in records
                ]
                for pid, records in self._history.items()
            }
            self._cache_path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _load(self):
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text())
                for pid, records in data.items():
                    self._history[pid] = [IterationRecord(**r) for r in records]
            except (json.JSONDecodeError, OSError, KeyError):
                pass
