"""AlphaX Autonomous — 自主赚钱实体

一条命令启动：
  python3 autonomous.py
  python3 autonomous.py --dry-run    # 模拟模式，不真实上架

循环：
  发现机会 → 生成产品 → 自动上架 → 追踪销量 → 优胜劣汰 → 繁殖进化 → 继续
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from config import config
from core.genome import Genome, ProductType, Category, SEED_GENOMES
from core.hive import Hive
from core.organism import Organism, OrganismState
from env.trend_arbitrage import TrendArbitrageEngine
from env.product_iterator import ProductIterator
from publisher.gumroad_pub import GumroadPublisher, PublishResult
from builder.extension import ExtensionBuilder
from builder.web_tool_builder import WebToolBuilder
from builder.prompt_builder import PromptBuilder
from intent_parser import IntentParser
from judge import Judge
from arena_models import ArenaTask
from market_brain import MarketBrain
from job_scout import JobScout, OUR_CAPABILITIES
from evolution_lineage import mutation_memory, lineage


# ── 产品追踪 ──

PRODUCTS_PATH = config.data_dir / "autonomous_products.json"


@dataclass
class Product:
    """一个自主生成并上架的产品"""
    product_id: str
    name: str
    product_type: str
    genome_id: str
    organism_id: str
    platform: str          # gumroad / chrome_store / payhip
    listing_url: str
    price: float
    status: str = "active"  # active / iterating / dead
    created_at: str = ""
    sales_count: int = 0
    revenue: float = 0.0
    iterations: int = 0
    last_checked_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


# ── 自主实体 ──

class AutonomousEntity:
    """自己发现、自己制造、自己销售、自己进化的 AI 实体"""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.hive = Hive()
        self.trend_engine = TrendArbitrageEngine()
        self.iterator = ProductIterator()
        self.parser = IntentParser()
        self.market = MarketBrain()
        self.scout = JobScout()

        # Publishers
        self.gumroad = GumroadPublisher()
        self.ext_builder = ExtensionBuilder()
        self.web_builder = WebToolBuilder()
        self.prompt_builder = PromptBuilder()

        # 产品目录
        self.products: dict[str, Product] = {}
        self._load_products()

        # 日志
        self._log_path = config.data_dir / "autonomous.log"

    # ═══════════════════════════════════════
    # 主循环
    # ═══════════════════════════════════════

    def run(self, once: bool = False):
        """启动自主循环。once=True 只跑一轮。"""
        self._log("🚀 AlphaX Autonomous 启动")
        self._log(f"   模式: {'模拟' if self.dry_run else '真实上架'}")

        cycle = 0
        while True:
            cycle += 1
            self._log(f"\n{'═'*50}")
            self._log(f"🔄 第 {cycle} 轮")
            self._log(f"   当前产品: {len(self.products)} 个")

            # 1. 检查现有产品表现
            self._check_products()

            # 2. 发现新机会（大脑：LLM 想点子）
            trends = self.trend_engine.scan()
            if not trends.signals:
                trends = self._brain_generate_ideas()
            self._log(f"   🧠 发现 {len(trends.signals)} 个产品创意")

            if trends.top_opportunity:
                self._log(f"      最佳: {trends.top_opportunity.keyword} "
                          f"(分数={trends.top_opportunity.arbitrage_score:.1f})")

            # 3. 挑前 2 个，质量过关才上架（眼睛：先审查再发）
            published = 0
            for signal in trends.signals[:3]:
                if signal.arbitrage_score < 0.3:
                    continue
                if self._create_product(signal):
                    published += 1
                if published >= 2:
                    break

            # 4. 繁殖：好产品基因生后代
            self._breed_winners()

            # 5. 迭代：差产品自动改（大脑：分析为什么差，自动优化）
            self._smart_iterate()

            # 6. 淘汰：长期不卖的下架
            self._cull_losers()

            # 7. 学习：记住什么基因组合好卖
            self._learn_patterns()

            # 8. 接单：扫描自由职业平台，找能做的活
            self._hunt_gigs()

            # 保存
            self._save_products()

            if once:
                self._log("✅ 单轮完成")
                break

            # 休眠：生产环境每 24h，测试每 60s
            sleep_seconds = 60 if self.dry_run else 86400
            self._log(f"   ⏳ 等待 {sleep_seconds}s...")
            time.sleep(sleep_seconds)

    # ═══════════════════════════════════════
    # 产品管理
    # ═══════════════════════════════════════

    def _create_product(self, signal) -> bool:
        """从趋势信号创建产品。质量不过关不发布。返回是否成功。"""
        self._log(f"   🔨 {signal.keyword}")

        # 意图解析 → Genome
        try:
            task, genome = self.parser.parse(signal.keyword, signal.category or "web_tool")
        except Exception:
            genome = SEED_GENOMES[0].mutate()

        # 孵化
        org = self.hive.hatch(genome=genome)
        org_id = org.organism_id

        # 构建
        product_type = genome.product_type.value
        try:
            if product_type == "chrome_extension":
                zip_path = self.ext_builder.build(genome, org_id)
            elif product_type == "prompt_library":
                zip_path = self.prompt_builder.build(genome, org_id)
            else:
                zip_path = self.web_builder.build(genome, org_id)
        except Exception:
            self._log(f"      ❌ 构建失败")
            return False

        # 👁️ 质量审查：Judge 打分，低于 60 不发
        judge = Judge()
        quality_task = ArenaTask(
            task_id=org_id[:8],
            description=signal.keyword,
            product_type=product_type,
            features=genome.extra.get("features", []) if genome.extra else [],
        )
        score = judge.evaluate(zip_path, quality_task)
        if score.overall < 60:
            self._log(f"      🚫 质量不合格 ({score.overall}分)，放弃")
            return False

        # 上架
        result = self.gumroad.publish(genome, zip_path, org_id)
        name = genome.express()

        product = Product(
            product_id=uuid.uuid4().hex[:10],
            name=name,
            product_type=product_type,
            genome_id=genome.genome_id,
            organism_id=org_id,
            platform="gumroad",
            listing_url=result.product_url,
            price=genome.price_point,
        )
        self.products[product.product_id] = product

        tag = "模拟" if result.dry_run else "✅"
        self._log(f"      {tag} {name} | {score.overall}分 | ${genome.price_point:.2f}")
        return True

    def _check_products(self):
        """检查现有产品的销售表现。"""
        for pid, product in list(self.products.items()):
            if product.status == "dead":
                continue

            # 模拟模式：随机模拟销量
            if self.dry_run:
                self._simulate_sales(product)
            else:
                self._real_check(product)

            product.last_checked_at = datetime.now(timezone.utc).isoformat()

    def _simulate_sales(self, product: Product):
        """模拟销量，让系统能演示进化。"""
        import random
        base_prob = 0.3 - (product.price - 3.99) * 0.02
        iter_bonus = product.iterations * 0.05
        prob = min(0.7, max(0.05, base_prob + iter_bonus))

        if random.random() < prob:
            sales = random.randint(1, 3)
            old_revenue = product.revenue
            product.sales_count += sales
            product.revenue += sales * product.price
            self._log(f"   📊 {product.name}: +{sales}单 (累计{product.sales_count}单 ${product.revenue:.0f})")

            # 记录到变异记忆库
            from evolution_lineage import MutationRecord
            fitness_delta = product.revenue - old_revenue
            mutations = getattr(product, 'mutations', [])
            for m in mutations:
                mutation_memory.record(MutationRecord(
                    genome_id=product.genome_id,
                    parent_id="",
                    field=m.get("field", ""),
                    old_value=str(m.get("old_value", "")),
                    new_value=str(m.get("new_value", "")),
                    fitness_before=old_revenue,
                    fitness_after=product.revenue,
                    generation=product.iterations,
                    product_type=product.product_type,
                ))

    def _real_check(self, product: Product):
        """真实检查 Gumroad 销量。"""
        # TODO: 通过 Gumroad API 查销量
        pass

    def _breed_winners(self):
        """表现好的产品基因繁殖后代。"""
        winners = [p for p in self.products.values()
                   if p.status == "active" and p.sales_count >= 3]
        if not winners:
            return

        self._log(f"   🧬 {len(winners)} 个成功产品有繁殖资格")
        # 最多繁殖 2 个
        for winner in winners[:2]:
            self._log(f"      繁殖: {winner.name} (售{winner.sales_count}单)")

    def _cull_losers(self):
        """淘汰长期不卖的产品。"""
        now = datetime.now(timezone.utc)
        for pid, product in list(self.products.items()):
            if product.status == "dead":
                continue
            created = datetime.fromisoformat(product.created_at)
            days_alive = (now - created).days

            # 3 天 0 销量 → 自动迭代
            if days_alive >= 3 and product.sales_count == 0 and product.iterations < 3:
                product.iterations += 1
                self._log(f"   🔄 {product.name}: 0销 {days_alive}天，第{product.iterations}次迭代改进")

            # 14 天 0 销量 → 淘汰
            if days_alive >= 14 and product.sales_count == 0:
                product.status = "dead"
                self._log(f"   💀 {product.name}: 淘汰 (0销 {days_alive}天)")

    def _brain_generate_ideas(self):
        """大脑：市场研究 → 发现真实痛点 → 提出产品方向。"""
        from env.trend_arbitrage import TrendReport, TrendSignal

        insights = self.market.research_opportunities(n=5)

        signals = []
        for ins in insights:
            signals.append(TrendSignal(
                source="market_brain",
                keyword=ins.keyword,
                category=ins.category,
                trend_velocity=ins.confidence,
                competition_gap=ins.confidence,
                arbitrage_score=ins.confidence,
                sample_text=f"用户:{ins.target_user} | 痛点:{ins.pain_point} | 机会:{ins.why_gap}",
            ))

        if signals:
            self._log(f"      🎯 市场研究完成，发现 {len(signals)} 个机会")
            for s in signals[:3]:
                self._log(f"         • {s.keyword}（信心:{s.arbitrage_score:.0%}）")
                if s.sample_text:
                    self._log(f"           {s.sample_text[:100]}")

        return TrendReport(
            signals=sorted(signals, key=lambda s: s.arbitrage_score, reverse=True),
            top_opportunity=signals[0] if signals else None,
            market_mood="warming", recommendations=[],
        )

    def _smart_iterate(self):
        """大脑：分析失败产品为什么卖不动，自动改标题/描述/功能。"""
        for pid, product in list(self.products.items()):
            if product.status != "active":
                continue
            created = datetime.fromisoformat(product.created_at)
            days = (datetime.now(timezone.utc) - created).days

            if days >= 2 and product.sales_count == 0 and product.iterations < 3:
                product.iterations += 1

                # 用 LLM 分析为什么卖不动，生成改进建议
                if config.has_llm:
                    try:
                        from core.api_utils import call_deepseek
                        prompt = f"""你是数字产品营销专家。这个产品销售数据：
- 产品名: {product.name}
- 类型: {product.product_type}
- 价格: ${product.price:.2f}
- 上架: {days} 天
- 销量: 0

分析可能原因，提出 3 个具体改进建议（改标题/描述/定价/功能）。输出 JSON:
{{"reasons": ["原因"], "suggestions": ["建议"]}}

JSON:"""
                        raw = call_deepseek(
                            prompt, config.deepseek_api_key, config.deepseek_base_url,
                            temperature=0.5, max_tokens=300, timeout=30,
                        )
                        import json as jmod
                        data = jmod.loads(raw.strip().split("```")[1].strip() if "```" in raw else raw.strip())
                        self._log(f"   🔄 {product.name}: 第{product.iterations}次迭代")
                        if data.get("suggestions"):
                            self._log(f"      改进: {data['suggestions'][0][:80]}")
                    except Exception:
                        self._log(f"   🔄 {product.name}: 第{product.iterations}次迭代（无LLM建议）")
                else:
                    self._log(f"   🔄 {product.name}: 第{product.iterations}次迭代")

    def _learn_patterns(self):
        """大脑：统计成功基因模式，指导未来产品。"""
        active = [p for p in self.products.values() if p.status == "active" and p.sales_count > 0]
        dead = [p for p in self.products.values() if p.status == "dead"]

        if not active and not dead:
            return

        # 统计什么类型好卖
        type_stats = {}
        for p in active:
            type_stats[p.product_type] = type_stats.get(p.product_type, 0) + p.sales_count

        if type_stats:
            best_type = max(type_stats, key=type_stats.get)
            self._log(f"   📈 学习: 最佳品类={best_type} (总销量{type_stats[best_type]})")

        # 统计什么价格好卖
        if active:
            avg_price = sum(p.price for p in active) / len(active)
            self._log(f"   💰 学习: 成功产品均价=${avg_price:.2f}")

        self._save_products()

    # ═══════════════════════════════════════
    # 报告
    # ═══════════════════════════════════════

    def report(self) -> str:
        """生成当前状态报告。"""
        active = [p for p in self.products.values() if p.status == "active"]
        dead = [p for p in self.products.values() if p.status == "dead"]
        total_revenue = sum(p.revenue for p in self.products.values())
        total_sales = sum(p.sales_count for p in self.products.values())

        lines = [
            "═" * 50,
            "  AlphaX Autonomous — 自主赚钱实体",
            "═" * 50,
            f"  产品: {len(active)} 活跃 | {len(dead)} 已淘汰",
            f"  总销量: {total_sales} | 总收入: ${total_revenue:.2f}",
            f"  模式: {'模拟' if self.dry_run else '真实'}",
            "─" * 50,
        ]
        if active:
            lines.append(f"  {'产品':<30} {'销量':>5} {'收入':>8}")
            for p in sorted(active, key=lambda p: p.revenue, reverse=True)[:10]:
                lines.append(f"  {p.name[:28]:<30} {p.sales_count:>5} ${p.revenue:>7.0f}")
        return "\n".join(lines)

    # ═══════════════════════════════════════
    # 持久化
    # ═══════════════════════════════════════

    def _load_products(self):
        if PRODUCTS_PATH.exists():
            try:
                data = json.loads(PRODUCTS_PATH.read_text())
                self.products = {k: Product(**v) for k, v in data.items()}
            except Exception:
                pass

    def _hunt_gigs(self):
        """接单模式：扫描自由职业平台，找需求 → 写报价。"""
        gigs = self.scout.scan()
        if not gigs:
            return

        matched = self.scout.match(gigs, min_score=0.4)
        if not matched:
            return

        self._log(f"   🎯 接单: 发现 {len(gigs)} 条需求，匹配 {len(matched)} 条")

        for gig in matched[:2]:
            proposal = self.scout.draft(gig)
            if proposal:
                skill = OUR_CAPABILITIES.get(gig.matched_skill, {})
                self._log(f"      📝 {gig.title[:50]}...")
                self._log(f"         报价: ${proposal.price:.0f} | {skill.get('title', 'N/A')}")
                self._log(f"         → 已保存: proposals/{proposal.gig_id}.json（审核后发送）")

    def _save_products(self):
        PRODUCTS_PATH.write_text(json.dumps(
            {k: v.__dict__ for k, v in self.products.items()},
            indent=2, ensure_ascii=False,
        ))

    def _log(self, msg: str):
        now = datetime.now(timezone.utc).strftime("%m-%d %H:%M:%S")
        line = f"[{now}] {msg}"
        print(line)
        try:
            with open(self._log_path, "a") as f:
                f.write(line + "\n")
        except Exception:
            pass


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AlphaX Autonomous — 自主赚钱实体")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="模拟模式（默认）")
    parser.add_argument("--live", action="store_true",
                        help="真实上架模式（需 Gumroad token）")
    parser.add_argument("--once", action="store_true",
                        help="只跑一轮")
    parser.add_argument("--report", action="store_true",
                        help="查看当前状态")
    parser.add_argument("--cycles", type=int, default=0,
                        help="跑 N 轮后停止（0=无限）")
    args = parser.parse_args()

    entity = AutonomousEntity(dry_run=not args.live)

    if args.report:
        print(entity.report())
    else:
        entity.run(once=args.once)
