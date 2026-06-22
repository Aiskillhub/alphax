"""AlphaX Publisher — Gumroad 发布

将构建好的 Chrome Extension zip 上架到 Gumroad。
支持 dry-run 模式（未配置 token 时）。
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path

from core.genome import Genome, Category, PricingModel
from config import config


@dataclass
class PublishResult:
    success: bool
    product_id: str = ""
    product_url: str = ""
    product_name: str = ""
    error: str = ""
    dry_run: bool = False


class GumroadPublisher:
    """将产品发布到 Gumroad 市场"""

    def publish(self, genome: Genome, zip_path: Path, organism_id: str) -> PublishResult:
        """发布产品到 Gumroad，返回发布结果"""
        name = genome.express()
        description = self._make_description(genome)
        price_cents = int(genome.price_point * 100)

        if not config.gumroad_access_token:
            return PublishResult(
                success=True,
                product_id=f"dry_{organism_id}",
                product_url=f"https://gumroad.com/l/dry-{organism_id}",
                product_name=name,
                dry_run=True,
            )

        try:
            data = json.dumps({
                "name": name,
                "description": description,
                "price": price_cents,
            }).encode()

            req = urllib.request.Request(
                "https://api.gumroad.com/v2/products",
                data=data,
                headers={
                    "Authorization": f"Bearer {config.gumroad_access_token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())

            product = result.get("product", {})
            return PublishResult(
                success=True,
                product_id=product.get("id", ""),
                product_url=product.get("short_url", ""),
                product_name=name,
            )
        except urllib.error.HTTPError as e:
            return PublishResult(
                success=False,
                product_name=name,
                error=f"HTTP {e.code}: {e.reason}",
            )
        except (urllib.error.URLError, OSError) as e:
            return PublishResult(
                success=False,
                product_name=name,
                error=str(e),
            )

    def _make_description(self, genome: Genome) -> str:
        pricing = {
            "one_time": "One-time purchase. Lifetime access.",
            "subscription": "Monthly subscription. Cancel anytime.",
            "freemium": "Free to use. Premium features available.",
        }
        return (
            f"{genome.benefit}\n\n"
            f"Features:\n"
            f"• Works on multiple AI platforms\n"
            f"• Export conversations in Markdown & Text\n"
            f"• Search across your chat history\n"
            f"• Clean, modern interface\n\n"
            f"{pricing.get(genome.pricing_model.value, '')}\n\n"
            f"Questions? Contact us anytime."
        )
