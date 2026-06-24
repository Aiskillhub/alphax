"""AlphaX Job Scout — AI 接单引擎

监控各平台需求 → 匹配能力 → 写报价 → 人审核 → 中标交付。

支持的平台：
  - Reddit r/forhire, r/slavelabour, r/jobbit
  - （扩展：Upwork MCP / Fiverr / 猪八戒）

用法：
  scout = JobScout()
  gigs = scout.scan()              # 扫描最新需求
  matched = scout.match(gigs)      # 匹配我们的能力
  proposal = scout.draft(gig)      # 写报价
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


# ── 能力清单 ──

OUR_CAPABILITIES = {
    "chrome_extension": {
        "title": "Chrome 浏览器扩展开发",
        "keywords": ["chrome", "extension", "浏览器", "扩展", "插件", "browser"],
        "price_range": (49, 199),
        "delivery_days": (1, 3),
        "description": "开发 Chrome 扩展，支持一键保存、翻译、自动化等",
    },
    "web_tool": {
        "title": "Web 工具/计算器开发",
        "keywords": ["web", "tool", "calculator", "工具", "计算器", "网页", "landing", "form", "表单"],
        "price_range": (39, 149),
        "delivery_days": (1, 2),
        "description": "单页 Web 工具，如计算器、格式化器、生成器",
    },
    "prompt_library": {
        "title": "AI 提示词/文案模板",
        "keywords": ["prompt", "提示词", "文案", "copy", "template", "模板", "ai内容"],
        "price_range": (19, 79),
        "delivery_days": (1, 1),
        "description": "批量生成 AI 提示词包、文案模板、话术库",
    },
    "vscode_extension": {
        "title": "VS Code 插件开发",
        "keywords": ["vscode", "extension", "plugin", "插件", "代码"],
        "price_range": (79, 299),
        "delivery_days": (2, 5),
        "description": "VS Code 扩展开发，如自动格式化、代码片段",
    },
    "notion_template": {
        "title": "Notion 模板设计",
        "keywords": ["notion", "template", "模板", "dashboard", "tracker"],
        "price_range": (29, 99),
        "delivery_days": (1, 2),
        "description": "Notion 效率模板，如项目管理、财务追踪、日记",
    },
}


@dataclass
class Gig:
    """一个接单机会"""
    gig_id: str
    title: str
    description: str
    budget: str = ""               # "$50-$100" 或 "negotiable"
    platform: str = "reddit"       # reddit / upwork / fiverr
    url: str = ""
    poster: str = ""
    posted_at: str = ""
    match_score: float = 0.0       # 0-1，匹配度
    matched_skill: str = ""        # 匹配到的我们的能力
    suggested_price: float = 0.0   # AI 建议报价


@dataclass
class Proposal:
    """一份报价草稿"""
    gig_id: str
    title: str
    body: str                      # 报价正文
    price: float
    delivery_days: int
    saved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class JobScout:
    """AI 接单引擎"""

    def __init__(self):
        self._api_key = config.deepseek_api_key
        self._base_url = config.deepseek_base_url
        self._proposals_dir = config.data_dir / "proposals"
        self._proposals_dir.mkdir(exist_ok=True)

    # ═══════════════════════════════════════
    # 扫描需求
    # ═══════════════════════════════════════

    def scan(self) -> list[Gig]:
        """扫描所有平台，返回最新需求列表。"""
        all_gigs = []
        all_gigs += self._scan_reddit()
        return all_gigs

    def _scan_reddit(self) -> list[Gig]:
        """扫描 Reddit 自由职业相关子版。"""
        subs = ["forhire", "slavelabour", "jobbit"]
        gigs = []

        for sub in subs:
            try:
                import urllib.request
                import json as jmod
                url = f"https://www.reddit.com/r/{sub}/new.json?limit=15"
                req = urllib.request.Request(url, headers={"User-Agent": "AlphaX/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = jmod.loads(resp.read())

                for post in data.get("data", {}).get("children", []):
                    d = post["data"]
                    title = d.get("title", "")
                    body = d.get("selftext", "")[:500]
                    if not body or len(body) < 30:
                        continue

                    gigs.append(Gig(
                        gig_id=d.get("id", ""),
                        title=title,
                        description=body,
                        budget=self._extract_budget(title + " " + body),
                        platform="reddit",
                        url=f"https://reddit.com{d.get('permalink', '')}",
                        poster=d.get("author", ""),
                        posted_at=datetime.fromtimestamp(
                            d.get("created_utc", 0), tz=timezone.utc
                        ).isoformat(),
                    ))
            except Exception:
                pass

        return gigs

    # ═══════════════════════════════════════
    # 匹配能力
    # ═══════════════════════════════════════

    def match(self, gigs: list[Gig], min_score: float = 0.4) -> list[Gig]:
        """分析哪些需求我们能做，打分排序。"""
        matched = []
        for gig in gigs:
            best_skill = ""
            best_score = 0.0

            for skill_id, skill in OUR_CAPABILITIES.items():
                score = self._match_score(gig, skill)
                if score > best_score:
                    best_score = score
                    best_skill = skill_id

            if best_score >= min_score:
                gig.match_score = best_score
                gig.matched_skill = best_skill
                skill = OUR_CAPABILITIES[best_skill]
                gig.suggested_price = round(
                    skill["price_range"][0] +
                    (skill["price_range"][1] - skill["price_range"][0]) * best_score,
                    0,
                )
                matched.append(gig)

        matched.sort(key=lambda g: g.match_score, reverse=True)
        return matched

    def _match_score(self, gig: Gig, skill: dict) -> float:
        """计算 gig 跟我们的某项技能的匹配度。简单关键词+预算匹配。"""
        text = (gig.title + " " + gig.description).lower()
        keywords = skill["keywords"]
        hits = sum(1 for kw in keywords if kw.lower() in text)
        keyword_score = min(1.0, hits / max(1, len(keywords) * 0.4))

        # 如果有 LLM，用它做更准的匹配
        if self._api_key and keyword_score > 0.3:
            try:
                from core.api_utils import call_deepseek
                prompt = f"""你是技术评估专家。判断我们能否做这个需求。

## 我们的能力
{skill['title']}: {skill['description']}
价格范围: ${skill['price_range'][0]}-${skill['price_range'][1]}
交付: {skill['delivery_days'][0]}-{skill['delivery_days'][1]} 天

## 客户需求
标题: {gig.title}
描述: {gig.description[:300]}
预算: {gig.budget}

## 任务
回复一个数字 0.0-1.0，表示我们的能力匹配度。
1.0=完美匹配 0.5=能做但要改 0=完全不对口

只回复数字:"""

                raw = call_deepseek(
                    prompt, self._api_key, self._base_url,
                    temperature=0.1, max_tokens=10, timeout=15,
                )
                llm_score = float(raw.strip())
                return max(0.0, min(1.0, llm_score))
            except Exception:
                pass

        return keyword_score

    # ═══════════════════════════════════════
    # 写报价
    # ═══════════════════════════════════════

    def draft(self, gig: Gig) -> Proposal | None:
        """为匹配的需求写报价草稿。"""
        skill = OUR_CAPABILITIES.get(gig.matched_skill)
        if not skill:
            return None

        body = self._generate_proposal(gig, skill)
        proposal = Proposal(
            gig_id=gig.gig_id,
            title=f"Re: {gig.title[:60]}",
            body=body,
            price=gig.suggested_price,
            delivery_days=skill["delivery_days"][0],
        )

        # 保存到文件，等人审核
        self._save_proposal(proposal, gig)
        return proposal

    def _generate_proposal(self, gig: Gig, skill: dict) -> str:
        """用 LLM 写报价。"""
        if self._api_key:
            try:
                from core.api_utils import call_deepseek
                prompt = f"""你是专业自由职业者。为以下需求写一份报价回复。

## 需求
{gig.title}
{gig.description[:300]}

## 你的能力
{skill['title']}: {skill['description']}

## 你的方案
价格: ${gig.suggested_price:.0f}
交付: {skill['delivery_days'][0]}-{skill['delivery_days'][1]} 天

## 要求
- 英文（因为是国外平台）
- 3-4 句话，简洁专业
- 不提 AI，假装是人在写
- 包含具体方案（怎么做）

报价回复:"""

                raw = call_deepseek(
                    prompt, self._api_key, self._base_url,
                    temperature=0.5, max_tokens=300, timeout=20,
                )
                return raw.strip()
            except Exception:
                pass

        return f"""Hi, I can help with this.

I have experience building {skill['title'].lower()} and can deliver a working solution within {skill['delivery_days'][0]}-{skill['delivery_days'][1]} days.

My approach: understand your requirements → build → test → deliver with documentation.

Price: ${gig.suggested_price:.0f}. Let me know if you'd like to discuss."""

    def _save_proposal(self, proposal: Proposal, gig: Gig):
        """保存报价草稿到 proposals/ 目录，等人审核后发送。"""
        fname = f"{proposal.gig_id}.json"
        data = {
            "proposal": proposal.__dict__,
            "gig": gig.__dict__,
        }
        (self._proposals_dir / fname).write_text(
            json.dumps(data, indent=2, ensure_ascii=False)
        )

    # ═══════════════════════════════════════
    # 辅助
    # ═══════════════════════════════════════

    def _extract_budget(self, text: str) -> str:
        """从文本中提取预算信息。"""
        import re
        patterns = [
            r'\$(\d+)\s*[-–]\s*\$(\d+)',  # $50-$100
            r'budget.*?\$(\d+)',             # budget $50
            r'\$(\d+)',                      # $50
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                if m.lastindex and m.lastindex >= 2:
                    return f"${m.group(1)}-${m.group(2)}"
                return f"~${m.group(1)}"
        return "negotiable"


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

if __name__ == "__main__":
    scout = JobScout()

    print("🔍 扫描各平台需求...")
    gigs = scout.scan()
    print(f"   发现 {len(gigs)} 条需求")

    matched = scout.match(gigs, min_score=0.3)
    print(f"   匹配 {len(matched)} 条能做")

    for g in matched[:5]:
        skill = OUR_CAPABILITIES.get(g.matched_skill, {})
        print(f"\n{'─'*50}")
        print(f"📋 {g.title}")
        print(f"   平台: {g.platform} | 预算: {g.budget} | 匹配: {g.match_score:.0%}")
        print(f"   能力: {skill.get('title', 'N/A')} | 建议报价: ${g.suggested_price:.0f}")
        print(f"   描述: {g.description[:150]}...")

        proposal = scout.draft(g)
        if proposal:
            print(f"\n   📝 自动报价草稿:")
            print(f"   {proposal.body[:200]}...")
            print(f"   → 已保存到 proposals/{proposal.gig_id}.json（请审核后发送）")
