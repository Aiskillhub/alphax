"""AGIStore 部署管线

将 Alpha X 产物直接发布到 AGIStore 市场，替代 Gumroad。
AGIStore REST API 连接器 + 销售数据回流。
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path

from config import config


@dataclass
class AGIStoreProduct:
    """AGIStore 上的一个产品"""
    skill_id: str
    slug: str
    name: str
    price: float
    downloads: int = 0
    purchases: int = 0
    revenue: float = 0.0
    rating: float = 0.0
    url: str = ""


@dataclass
class DeployResult:
    """一次部署的结果"""
    success: bool
    skill_id: str = ""
    agistore_url: str = ""
    slug: str = ""
    error: str = ""


class AGIStoreDeployer:
    """AGIStore API 部署管线"""

    def __init__(self):
        self._token = config.agistore_api_token
        self._base_url = config.agistore_api_url.rstrip("/")
        self._cache_path = config.data_dir / "agistore_products.json"
        self._products: dict[str, AGIStoreProduct] = {}
        self._load()

    @property
    def is_available(self) -> bool:
        return bool(self._token)

    def deploy(self, organism, build, marketing_assets=None) -> DeployResult:
        """将一个 build 发布到 AGIStore"""
        if not self._token:
            return DeployResult(False, error="No AGIStore API token configured")

        genome = organism.genome

        # 产品名
        if marketing_assets and getattr(marketing_assets, 'suggested_title', None):
            name = marketing_assets.suggested_title
        elif genome and hasattr(genome, 'express'):
            name = genome.express()
        else:
            name = f"AI Agent #{organism.organism_id[:8]}"

        # 描述
        if marketing_assets and getattr(marketing_assets, 'description_seo', None):
            desc = marketing_assets.description_seo
        elif genome:
            desc = self._build_description(genome)
        else:
            desc = "An AI-generated agent."

        long_desc = ""
        if marketing_assets:
            parts = []
            if getattr(marketing_assets, 'bullet_points', None):
                parts.append("\n".join(f"• {bp}" for bp in marketing_assets.bullet_points))
            if getattr(marketing_assets, 'pricing_copy', None):
                parts.append(marketing_assets.pricing_copy)
            long_desc = "\n\n".join(parts)

        # 类别映射
        cat = self._map_category(genome)
        runtime = self._map_runtime(genome)
        price = float(getattr(genome, 'price_point', 0) if genome else 0)

        # 构建文件列表
        files = []
        if build.files:
            for fname, content in build.files.items():
                if isinstance(content, dict):
                    content = json.dumps(content, indent=2)
                files.append({"path": fname, "content": content})

        # 构建 payload
        payload = {
            "name": name,
            "description": desc[:500],
            "longDescription": long_desc[:5000] if long_desc else desc[:500],
            "category": cat,
            "platform": "agent",
            "price": price,
            "sourceType": "alphax",
            "originId": organism.organism_id,
            "runtime": runtime,
            "files": files,
            "changelog": f"Alpha X gen {genome.generation if genome else 1}",
            "icon": self._pick_icon(genome),
            "tags": self._build_tags(genome),
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self._base_url}/api/publish/agent",
                data=data,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())

            skill_id = result.get("id", "")
            slug = result.get("slug", "")
            agistore_url = result.get("url", "")

            if not skill_id:
                return DeployResult(False, error="AGIStore returned no skill ID")

            product = AGIStoreProduct(
                skill_id=skill_id,
                slug=slug,
                name=name,
                price=price,
                url=agistore_url,
            )
            self._products[skill_id] = product
            self._save()

            return DeployResult(
                success=True,
                skill_id=skill_id,
                slug=slug,
                agistore_url=agistore_url,
            )

        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            return DeployResult(False, error=f"AGIStore API error {e.code}: {error_body[:200]}")
        except Exception as e:
            return DeployResult(False, error=str(e))

    def fetch_stats(self, skill_id: str = "", origin_id: str = "") -> dict:
        """拉取产品销售数据"""
        if not self._token:
            return {}

        try:
            url = f"{self._base_url}/api/publish/agent/{skill_id}/stats"
            if origin_id:
                url += f"?originId={origin_id}"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {self._token}"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                # 更新本地缓存
                sid = data.get("id", "")
                if sid in self._products:
                    self._products[sid].downloads = data.get("downloads", 0)
                    self._products[sid].purchases = data.get("purchases", 0)
                    self._products[sid].revenue = data.get("revenue", 0)
                self._save()
                return data
        except Exception:
            pass

        return {}

    def fetch_all_sales(self) -> dict[str, dict]:
        """拉取所有已部署产品的销售数据"""
        all_sales = {}
        for sid in list(self._products.keys()):
            stats = self.fetch_stats(skill_id=sid)
            if stats:
                all_sales[sid] = stats
        return all_sales

    def unpublish(self, skill_id: str) -> bool:
        """下架产品（organism 死亡时调用）"""
        if not self._token:
            return False
        # AGIStore currently doesn't have an unpublish endpoint;
        # product remains in marketplace but marked with organism status
        return True

    def _map_category(self, genome) -> str:
        if not genome:
            return "other"
        cat_val = str(getattr(genome, 'category', 'other'))
        # Map Alpha X categories to AGIStore categories
        mapping = {
            "ai_chat": "ai_chat",
            "productivity": "productivity",
            "dev_tools": "dev_tools",
            "data": "data",
            "content": "content",
            "seo": "seo",
            "automation": "automation",
        }
        return mapping.get(cat_val.lower() if hasattr(cat_val, 'lower') else cat_val, "other")

    def _map_runtime(self, genome) -> str:
        if not genome:
            return "cli"
        ptype = str(getattr(genome, 'product_type', '')).lower()
        mapping = {
            "chrome_extension": "chrome_extension",
            "web_tool": "web",
            "api_service": "mcp",
            "vscode_extension": "cli",
            "notion_template": "cli",
            "prompt_library": "cli",
            "saas_boilerplate": "cli",
            "canva_template": "cli",
            "micro_course": "cli",
        }
        return mapping.get(ptype, "cli")

    def _pick_icon(self, genome) -> str:
        icons = {
            "chrome_extension": "🧩",
            "web_tool": "🌐",
            "api_service": "🔌",
            "vscode_extension": "💻",
            "prompt_library": "📝",
            "notion_template": "📋",
            "saas_boilerplate": "🏗️",
            "micro_course": "📚",
        }
        if genome:
            ptype = str(getattr(genome, 'product_type', '')).lower()
            return icons.get(ptype, "🤖")
        return "🤖"

    def _build_tags(self, genome) -> list[str]:
        if not genome:
            return ["ai", "agent"]
        tags = ["alpha-x", "ai-generated"]
        tags.append(str(getattr(genome, 'category', '')).lower())
        tags.append(str(getattr(genome, 'product_type', '')).lower())
        return tags

    def _build_description(self, genome) -> str:
        cat = str(getattr(genome, 'category', 'Dev Tools'))
        ptype = str(getattr(genome, 'product_type', 'Digital Tool'))
        audience = str(getattr(genome, 'target_audience', 'developers'))
        return f"A {ptype} for {audience}. Category: {cat}. Generated by Alpha X Evolution Engine."

    @property
    def summary(self) -> dict:
        return {
            "available": self.is_available,
            "products_listed": len(self._products),
            "total_downloads": sum(p.downloads for p in self._products.values()),
            "total_revenue": f"${sum(p.revenue for p in self._products.values()):.2f}",
        }

    def _save(self):
        try:
            data = {
                sid: {
                    "skill_id": p.skill_id,
                    "slug": p.slug,
                    "name": p.name,
                    "price": p.price,
                    "downloads": p.downloads,
                    "purchases": p.purchases,
                    "revenue": p.revenue,
                    "rating": p.rating,
                    "url": p.url,
                }
                for sid, p in self._products.items()
            }
            self._cache_path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _load(self):
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text())
                for sid, d in data.items():
                    self._products[sid] = AGIStoreProduct(**d)
            except (json.JSONDecodeError, OSError):
                pass
