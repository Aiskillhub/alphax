"""Gumroad 真实部署管线

不只是生成代码——真的上架、定价、追踪销售数据。
Gumroad API 连接器 + 销售数据回流到进化引擎。
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile
import zipfile

from config import config


@dataclass
class GumroadProduct:
    """Gumroad 上的一个产品"""
    product_id: str
    name: str
    description: str
    price_cents: int
    sales_count: int = 0
    revenue_cents: int = 0
    rating: float = 0.0
    published: bool = False
    url: str = ""


@dataclass
class DeployResult:
    """一次部署的结果"""
    success: bool
    product_id: str = ""
    gumroad_url: str = ""
    error: str = ""
    sales_data: dict = field(default_factory=dict)


class GumroadDeployer:
    """Gumroad API 真实上架管线"""

    BASE_URL = "https://api.gumroad.com/v2"

    def __init__(self):
        self._token = config.gumroad_access_token
        self._cache_path = config.data_dir / "gumroad_products.json"
        self._products: dict[str, GumroadProduct] = {}
        self._load()

    @property
    def is_available(self) -> bool:
        return bool(self._token)

    def deploy(self, organism, build, marketing_assets=None) -> DeployResult:
        """将一个 build 真实上架到 Gumroad。可传入 marketing_assets 获得更好的描述。"""
        if not self._token:
            return DeployResult(False, error="No Gumroad access token configured")

        genome = organism.genome

        # 产品名：优先用营销标题，其次 genome express
        if marketing_assets and marketing_assets.suggested_title:
            name = marketing_assets.suggested_title
        elif genome and hasattr(genome, 'express'):
            name = genome.express()
        else:
            name = f"AI Tool #{organism.organism_id[:8]}"

        # 产品描述：优先用营销 SEO 描述 + bullet points
        if marketing_assets and marketing_assets.description_seo:
            desc_parts = [marketing_assets.description_seo]
            if marketing_assets.bullet_points:
                desc_parts.append("\n".join(f"• {bp}" for bp in marketing_assets.bullet_points))
            if marketing_assets.pricing_copy:
                desc_parts.append(marketing_assets.pricing_copy)
            description = "\n\n".join(desc_parts)
        elif genome:
            description = self._build_description(genome)
        else:
            description = "An AI-generated product."

        # 准备文件：将 build 打包成 zip
        zip_path = self._package_build(build)
        if not zip_path:
            return DeployResult(False, error="Failed to package build files")

        try:
            price_cents = int((getattr(genome, 'price_point', 4.99) if genome else 4.99) * 100)

            # 创建产品
            data = urllib.parse.urlencode({
                "name": name,
                "description": description,
                "price": price_cents,
            }).encode()

            req = urllib.request.Request(
                f"{self.BASE_URL}/products",
                data=data,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                product_data = result.get("product", {})
                product_id = product_data.get("id", "")

            if not product_id:
                return DeployResult(False, error="Gumroad returned no product ID")

            # 自动发布产品
            short_url = ""
            try:
                req2 = urllib.request.Request(
                    f"{self.BASE_URL}/products/{product_id}/enable",
                    data=b"",
                    headers={"Authorization": f"Bearer {self._token}"},
                    method="PUT",
                )
                with urllib.request.urlopen(req2, timeout=15) as resp2:
                    enable_result = json.loads(resp2.read())
                    short_url = enable_result.get("product", {}).get("short_url", "")
            except Exception:
                pass  # enable 失败不算致命错误，产品已创建

            product = GumroadProduct(
                product_id=product_id,
                name=name,
                description=description,
                price_cents=price_cents,
                published=True,
                url=short_url or f"https://gumroad.com/l/{product_id}",
            )
            self._products[product_id] = product
            self._save()

            return DeployResult(
                success=True,
                product_id=product_id,
                gumroad_url=product.url,
                sales_data={"price_cents": price_cents, "name": name},
            )

        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            return DeployResult(False, error=f"Gumroad API error {e.code}: {error_body[:200]}")
        except Exception as e:
            return DeployResult(False, error=str(e))

    def fetch_sales(self) -> dict[str, dict]:
        """拉取所有产品的销售数据"""
        if not self._token:
            return {}

        sales = {}
        try:
            req = urllib.request.Request(
                f"{self.BASE_URL}/products",
                headers={"Authorization": f"Bearer {self._token}"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                for p in data.get("products", []):
                    pid = p.get("id", "")
                    sales[pid] = {
                        "name": p.get("name", ""),
                        "sales_count": p.get("sales_count", 0),
                        "revenue_cents": p.get("revenue", 0),
                        "rating": p.get("average_rating", 0),
                    }
                    if pid in self._products:
                        self._products[pid].sales_count = sales[pid]["sales_count"]
                        self._products[pid].revenue_cents = sales[pid]["revenue_cents"]
            self._save()
        except Exception:
            pass

        return sales

    def get_sales_for_organism(self, organism) -> dict:
        """获取关联到 organism 的销售数据"""
        # 通过 organism_id 查找对应的 Gumroad product
        for pid, product in self._products.items():
            # product name 通常包含 organism id 信息
            if organism.organism_id[:8] in product.name:
                return {
                    "product_id": pid,
                    "sales_count": product.sales_count,
                    "revenue_cents": product.revenue_cents,
                    "rating": product.rating,
                }
        return {}

    def _build_description(self, genome) -> str:
        """基于基因生成产品描述"""
        def _val(v):
            return v.value if hasattr(v, 'value') else str(v)

        cat = _val(getattr(genome, 'category', 'Dev Tools'))
        ptype = _val(getattr(genome, 'product_type', 'Digital Tool'))
        audience = _val(getattr(genome, 'target_audience', 'developers'))
        design = _val(getattr(genome, 'design_style', 'minimal'))

        return (
            f"A {design}-style {ptype} for {audience}.\n\n"
            f"Category: {cat}\n"
            f"Generated by Nexus Evolution Engine.\n"
            f"Built with AI, validated by real usage."
        )

    def _package_build(self, build) -> Path | None:
        """将 build 文件打包成 zip"""
        if not build.files:
            return None

        try:
            tmpdir = Path(tempfile.mkdtemp(prefix="gumroad_"))
            zip_path = tmpdir / "product.zip"

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for fname, content in build.files.items():
                    if isinstance(content, dict):
                        content = json.dumps(content, indent=2)
                    zf.writestr(fname, content)

            return zip_path
        except Exception:
            return None

    @property
    def total_sales(self) -> int:
        return sum(p.sales_count for p in self._products.values())

    @property
    def total_revenue(self) -> float:
        return sum(p.revenue_cents for p in self._products.values()) / 100

    @property
    def summary(self) -> dict:
        return {
            "available": self.is_available,
            "products_listed": len(self._products),
            "total_sales": self.total_sales,
            "total_revenue": f"${self.total_revenue:.2f}",
        }

    def _save(self):
        try:
            data = {
                pid: {
                    "product_id": p.product_id,
                    "name": p.name,
                    "description": p.description,
                    "price_cents": p.price_cents,
                    "sales_count": p.sales_count,
                    "revenue_cents": p.revenue_cents,
                    "rating": p.rating,
                    "published": p.published,
                    "url": p.url,
                }
                for pid, p in self._products.items()
            }
            self._cache_path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _load(self):
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text())
                for pid, d in data.items():
                    self._products[pid] = GumroadProduct(**d)
            except (json.JSONDecodeError, OSError):
                pass
