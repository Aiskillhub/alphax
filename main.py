#!/usr/bin/env python3
"""AlphaX — 自主深度进化引擎

NexusEngine 7层递归进化: Observer → Reflector → Mutator → Creator → Critic → Executor → Deployer

用法:
  python3 main.py                              # NexusEngine 30 代深度进化
  python3 main.py --generations 60             # 60 代
  python3 main.py --dry-run --generations 1    # 干跑测试
  python3 main.py --engine sim --days 30       # 旧版启发式模拟

环境变量:
  DEEPSEEK_API_KEY     DeepSeek API 密钥（NexusEngine 必需）
  AGISTORE_API_TOKEN   AGIStore API Token（发布到市场）
  AGISTORE_API_URL     AGIStore 地址（默认 http://localhost:3005）
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone

from config import config
from core.genome import SEED_GENOMES
from core.hive import Hive
from core.organism import OrganismState
from brain.memory import MemorySystem
from brain.knowledge import KnowledgeEngine
from brain.alpha_brain import AlphaBrain
from builder.extension import ExtensionBuilder
from builder.notion_builder import NotionBuilder
from builder.vscode_builder import VSCodeBuilder
from builder.prompt_builder import PromptBuilder
from builder.web_tool_builder import WebToolBuilder
from builder.tester import ExtensionTester
from builder.listing import ListingGenerator
from capital.fund import Fund
from monitor.market_monitor import MarketMonitor
from publisher.gumroad_pub import GumroadPublisher
from publisher.storefront import add_to_store
from publisher.cross_platform import CrossPlatformEngine
from publisher.agent_marketplace import get_marketplace, MarketplaceDB

# Layer 1: Agent-Native
from layer1.semantic_git import SemanticGit, ChangeType
from layer1.intent_code import IntentCode
from layer1.autonomous_ci import AutonomousCI

# Layer 4: Agent Economy
from layer4.service_directory import ServiceDirectory, Capability
from layer4.bidding_engine import BiddingEngine
from layer4.escrow import Escrow
from layer4.reputation import ReputationSystem

# ── 日志 ──
log = logging.getLogger("alphax")


def _check_credentials() -> list[str]:
    """启动时检查关键凭证，返回缺失列表"""
    warnings = []
    if not config.deepseek_api_key:
        warnings.append("DEEPSEEK_API_KEY — AlphaBrain 将降级为启发式模式")
    if not config.gumroad_access_token:
        warnings.append("GUMROAD_ACCESS_TOKEN — Gumroad 部署仅限于干跑")
    if not config.stripe_secret_key:
        warnings.append("STRIPE_SECRET_KEY — Storefront 支付未启用")
    if not config.chrome_client_id:
        warnings.append("CHROME_CLIENT_ID — Chrome Web Store 发布不可用")
    return warnings


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ── 初始化 ──

def seed_gene_pool(hive: Hive) -> None:
    for seed in SEED_GENOMES:
        variant = seed.mutate()
        hive.gene_pool[variant.genome_id] = variant
    log.info(f"基因库初始化: {len(hive.gene_pool)} 种子基因")


# ── 每日循环 ──

# ── DEPRECATED: 旧版启发式模拟，保留作为 fallback（--engine sim）──

def run_day(
    day: int,
    hive: Hive,
    fund: Fund,
    memory: MemorySystem,
    knowledge: KnowledgeEngine,
    alpha: AlphaBrain,
    builder: ExtensionBuilder,
    notion_builder: NotionBuilder,
    vscode_builder: VSCodeBuilder,
    prompt_builder: PromptBuilder,
    webtool_builder: WebToolBuilder,
    tester: ExtensionTester,
    publisher: GumroadPublisher,
    monitor: MarketMonitor,
    listing_gen: ListingGenerator,
    semgit: SemanticGit,
    intent_code: IntentCode,
    auto_ci: AutonomousCI,
    service_dir: ServiceDirectory,
    bidding: BiddingEngine,
    escrow: Escrow,
    reputation: ReputationSystem,
    cross_platform: CrossPlatformEngine,
    dry_run: bool = False,
) -> str:
    events = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Alpha Brain 智能孵化
    if fund.can_hatch and len(hive.active_organisms) < config.max_population:
        training = memory.get_training_data()
        force_explore = hive.diversity < config.min_population_diversity

        for _ in range(random.randint(1, 3)):
            if not fund.can_hatch or len(hive.active_organisms) >= config.max_population:
                break

            decision = alpha.decide(
                gene_pool=hive.gene_pool,
                fund_balance=fund.pool_balance,
                training_data=training,
                force_explore=force_explore,
            )
            org = hive.hatch(genome=decision.genome, strategy="inherit")
            fund.spend_hatch(org.organism_id)
            log.debug(f"孵化: {decision.genome.express()} [{decision.source}]")

    # 2. 构建 + 测试 + 文案 + 发布 (多品类 + 跨平台)
    deployed = _build_and_deploy(
        hive, builder, notion_builder, vscode_builder, prompt_builder,
        webtool_builder,
        tester, publisher, memory, listing_gen,
        semgit, intent_code, auto_ci, cross_platform, today)

    if deployed:
        events.append(f"发布 {len(deployed)} 个")
        # Layer 4: 注册为服务 Agent
        for org in deployed:
            _register_agent(org, service_dir)

    # 3. 每日心跳
    tick_data = monitor.poll(hive.organisms)
    tick_events = hive.tick_all(tick_data)

    for e in tick_events:
        if e.startswith("DEATH:"):
            _handle_death(e, hive, fund, memory, knowledge, service_dir, events)
        elif e.startswith("BREED_READY:"):
            events.append(e)

    # 4. 收入分配
    for oid, data in tick_data.items():
        org = hive.organisms.get(oid)
        if org and org.is_alive and data.get("income", 0) > 0:
            fund.distribute_income(data["income"], oid)

    # 5. 繁殖
    children = hive.breed_top(n=2)
    for child in children:
        if fund.can_hatch:
            fund.spend_hatch(child.organism_id)
            _record_breed(child, hive, memory, knowledge)

    # 6. Agent Economy 每日循环
    economy_events = _run_agent_economy(day, hive, service_dir, bidding, escrow, reputation)
    if economy_events:
        events.extend(economy_events)

    # 7. 持久化
    if not dry_run:
        hive.save()
        fund.save()

    return f"[Day {day:3d}] {today} | {'; '.join(events) if events else '无事发生'}"


def _build_and_deploy(hive, builder, notion_builder, vscode_builder, prompt_builder,
                      webtool_builder,
                      tester, publisher, memory, listing_gen,
                      semgit, intent_code, auto_ci, cross_platform, today) -> list:
    """构建、测试、生成文案、发布所有待部署个体 (多品类 + 跨平台)"""
    from core.genome import ProductType

    deployed = []
    for org in hive.organisms.values():
        if org.state != OrganismState.HATCHING or not org.genome:
            continue

        try:
            genome = org.genome

            # 根据产品类型选择构建器
            if genome.product_type == ProductType.CHROME_EXTENSION:
                zip_path = builder.build(genome, org.organism_id)
                build_dir = builder._build_dir / org.organism_id
            elif genome.product_type == ProductType.NOTION_TEMPLATE:
                zip_path = notion_builder.build(genome, org.organism_id)
                build_dir = notion_builder._build_dir / f"notion_{org.organism_id}"
            elif genome.product_type == ProductType.VSCODE_EXTENSION:
                zip_path = vscode_builder.build(genome, org.organism_id)
                build_dir = vscode_builder._build_dir / f"vscode_{org.organism_id}"
            elif genome.product_type == ProductType.PROMPT_LIBRARY:
                zip_path = prompt_builder.build(genome, org.organism_id)
                build_dir = prompt_builder._build_dir / f"prompt_{org.organism_id}"
            elif genome.product_type == ProductType.WEB_TOOL:
                zip_path = webtool_builder.build(genome, org.organism_id)
                build_dir = webtool_builder._build_dir / f"webtool_{org.organism_id}"
            else:
                zip_path = builder.build(genome, org.organism_id)
                build_dir = builder._build_dir / org.organism_id

            # 基本验证（非 extension 类型跳过技术验证）
            if genome.product_type == ProductType.CHROME_EXTENSION:
                test_result = tester.validate(build_dir)
                if not test_result.passed:
                    log.warning(f"构建测试失败: {genome.express()}: {test_result.summary}")
                    memory.record_insight("build_fail",
                        f"{genome.express()}: {test_result.summary}", 0.6)
                    org.energy -= 1
                    continue
            else:
                # 非 extension 类型：检查是否有产物
                if not list(build_dir.iterdir()):
                    log.warning(f"构建空产物: {genome.express()}")
                    org.energy -= 1
                    continue

            # 生成商品文案
            listing = listing_gen.generate(genome)
            (build_dir / "listing.json").write_text(
                _listing_to_json(listing))

            # ── Layer 1: 收集构建产物 ──
            files = {}
            for f in build_dir.iterdir():
                if f.is_file():
                    try:
                        files[f.name] = f.read_text()[:2000]
                    except Exception:
                        pass

            intent = f"Build {genome.express()}: {genome.benefit}"
            genome_id = genome.genome_id

            # Layer 1: 语义 Git commit
            semgit.commit(
                intent=intent,
                change_type=ChangeType.FEATURE,
                files=list(files.keys()),
                agent_id=org.organism_id,
                organism_id=org.organism_id,
                genome_id=genome_id,
                before="",
                after=f"{genome.product_type.value} built with {len(files)} files",
            )

            # Layer 1: 意图代码存储
            intent_code.store(
                intent=intent,
                files=files,
                organism_id=org.organism_id,
                genome_id=genome_id,
            )

            # Layer 1: 自主 CI
            if semgit.commits:
                ci_run = auto_ci.run(
                    commit_id=semgit.commits[-1].commit_id,
                    organism_id=org.organism_id,
                    files=files,
                    intent=intent,
                )
                if ci_run.status.value == "merged":
                    log.debug(f"CI passed: {ci_run.pass_rate:.0%}")

            # ── 跨平台发布 ──
            result = publisher.publish(genome, zip_path, org.organism_id)
            if result.success:
                org.gumroad_product_id = result.product_id
                org.deploy()
                memory.record_deploy(org.organism_id, genome.genome_id, result.product_name)
                deployed.append(org)
                log.info(f"发布: {result.product_name} [{genome.product_type.value}]")

                # 跨平台分发
                channel_rec = cross_platform.channel_recommendation(genome)
                platforms = ["self_hosted"] + channel_rec["secondary"]
                cross_platform.list_product(
                    product_id=org.organism_id,
                    name=genome.express(),
                    description=genome.benefit,
                    base_price=genome.price_point,
                    tags=[genome.category.value, genome.product_type.value],
                    platforms=platforms,
                )

                # 同步到自建商店
                add_to_store(
                    product_id=org.organism_id,
                    name=genome.express(),
                    description=genome.benefit,
                    price=genome.price_point,
                    product_type=genome.product_type.value,
                )
                log.debug(f"  跨平台: {', '.join(platforms)}")
            else:
                log.warning(f"发布失败: {result.product_name}: {result.error}")
                memory.record_insight("publish_fail",
                    f"{result.product_name}: {result.error}", 0.5)

        except Exception as e:
            log.error(f"构建异常: {e}")
            memory.record_insight("build_error", str(e), 0.5)

    return deployed


def _listing_to_json(listing) -> str:
    import json
    return json.dumps({
        "title": listing.title,
        "subtitle": listing.subtitle,
        "description": listing.description,
        "bullets": listing.bullets,
        "target_audience": listing.target_audience,
        "seo_keywords": listing.seo_keywords,
    }, indent=2, ensure_ascii=False)


def _handle_death(event: str, hive, fund, memory, knowledge, service_dir, events: list):
    """处理个体死亡事件"""
    _, oid, name = event.split(":", 2)
    org = hive.organisms.get(oid)
    if not org or not org.genome:
        return

    memory.record_result(
        organism_id=oid,
        genome_id=org.genome.genome_id,
        days_alive=org.days_alive,
        total_earned=org.total_earned,
        total_burned=org.total_burned,
        survived=False,
        avg_rating=org.current_rating,
    )

    knowledge.learn_from_result(
        category=org.genome.category.value,
        price_point=org.genome.price_point,
        pricing_model=org.genome.pricing_model.value,
        target_market=org.genome.target_market.value,
        competition="medium",
        result={
            "survived": False,
            "net_profit": round(org.total_earned - org.total_burned, 2),
            "days_alive": org.days_alive,
        },
    )

    # Layer 4: 从服务目录注销
    service_dir.unregister(oid)
    # Layer 4: 记录最终信誉
    reputation.record_deal_complete(oid, success=False)

    revenue = org.total_earned - org.total_burned
    events.append(f"死亡: {name}({org.days_alive}d, ${revenue:.0f})")
    log.info(f"死亡: {name} 存活{org.days_alive}d 净${revenue:.2f}")

    if org.total_earned > 0:
        fund.distribute_income(org.total_earned, oid)


def _record_breed(child, hive, memory, knowledge):
    """记录繁殖事件"""
    if not child.parent_organism_id:
        return
    parent = hive.organisms.get(child.parent_organism_id)
    if not parent or not parent.genome:
        return

    memory.record_result(
        organism_id=parent.organism_id,
        genome_id=parent.genome.genome_id,
        days_alive=parent.days_alive,
        total_earned=parent.total_earned,
        total_burned=parent.total_burned,
        survived=True,
        avg_rating=parent.current_rating,
    )
    knowledge.learn_from_result(
        category=parent.genome.category.value,
        price_point=parent.genome.price_point,
        pricing_model=parent.genome.pricing_model.value,
        target_market=parent.genome.target_market.value,
        competition="medium",
        result={
            "survived": True,
            "net_profit": round(parent.total_earned - parent.total_burned, 2),
            "days_alive": parent.days_alive,
        },
    )


# ── Layer 4: Agent Economy ──

def _register_agent(org, service_dir: ServiceDirectory):
    """部署后将 Organism 注册为服务 Agent"""
    if not org.genome:
        return
    genome = org.genome

    # 根据基因组类别生成能力标签
    capabilities = _genome_capabilities(genome)

    name = genome.express()
    service_dir.register(
        organism_id=org.organism_id,
        name=name,
        capabilities=capabilities,
        base_price=round(genome.price_point * 1.5, 2),
    )


def _genome_capabilities(genome) -> list:
    """从基因组推断 Agent 能力"""
    from core.genome import Category

    caps = []
    cat = genome.category

    if cat == Category.AI_CHAT:
        caps.append(Capability(
            name="chat_export", description="导出 AI 对话为 Markdown/PDF/Text",
            input_schema={"format": "string"}, output_schema={"file": "string"},
            avg_quality=0.7, avg_latency_ms=500,
        ))
        caps.append(Capability(
            name="conversation_search", description="全文搜索对话历史",
            input_schema={"query": "string"}, output_schema={"results": "array"},
            avg_quality=0.65, avg_latency_ms=300,
        ))
    elif cat == Category.PRODUCTIVITY:
        caps.append(Capability(
            name="task_capture", description="快速捕获网页内容为任务",
            input_schema={"url": "string"}, output_schema={"task": "object"},
            avg_quality=0.6, avg_latency_ms=400,
        ))
        caps.append(Capability(
            name="note_organize", description="整理和分类笔记",
            input_schema={"notes": "array"}, output_schema={"organized": "array"},
            avg_quality=0.55, avg_latency_ms=600,
        ))
    elif cat == Category.DEV_TOOLS:
        caps.append(Capability(
            name="tech_inspect", description="检测网页技术栈",
            input_schema={"url": "string"}, output_schema={"stack": "array"},
            avg_quality=0.75, avg_latency_ms=200,
        ))
        caps.append(Capability(
            name="code_review", description="审查扩展代码质量",
            input_schema={"code": "string"}, output_schema={"review": "object"},
            avg_quality=0.6, avg_latency_ms=1000,
        ))
    else:
        caps.append(Capability(
            name="content_extract", description="提取网页结构化内容",
            input_schema={"url": "string"}, output_schema={"data": "object"},
            avg_quality=0.5, avg_latency_ms=800,
        ))

    # 所有 Agent 都有 listing_copy 能力（从 ListingGenerator 衍生）
    caps.append(Capability(
        name="listing_copy", description="生成 Gumroad 商品文案",
        input_schema={"product": "object"}, output_schema={"copy": "object"},
        avg_quality=0.55, avg_latency_ms=1500,
    ))

    return caps


def _run_agent_economy(
    day: int,
    hive,
    service_dir: ServiceDirectory,
    bidding: BiddingEngine,
    escrow: Escrow,
    reputation: ReputationSystem,
) -> list[str]:
    """每日 Agent Economy 循环"""
    events = []
    active = hive.active_organisms

    # 跳过前 3 天（积累足够 Agent）
    if day < 3 or len(active) < 3:
        return events

    # 1. 随机选择 1-2 个 Agent 发布需求
    import random as _random
    demanders = _random.sample(active, min(2, len(active)))
    capabilities_pool = ["code_review", "listing_copy", "tech_inspect", "chat_export"]

    for org in demanders:
        if not org.genome:
            continue
        cap = _random.choice(capabilities_pool)
        demand = bidding.post_demand(
            requester_id=org.organism_id,
            capability=cap,
            description=f"Need {cap} for {org.genome.express()}",
            max_budget=_random.uniform(1.0, 5.0),
        )
        events.append(f"需求: {cap}")

        # 2. 匹配的 Agent 自动竞标
        candidates = service_dir.find_by_capability(cap)
        for candidate in candidates[:3]:
            if candidate.agent_id == org.organism_id:
                continue
            bid = bidding.place_bid(
                demand_id=demand.demand_id,
                bidder_id=candidate.agent_id,
                price=round(_random.uniform(0.5, demand.max_budget), 2),
                estimated_quality=_random.uniform(0.5, 0.9),
                estimated_hours=_random.uniform(1.0, 8.0),
            )
            if bid:
                # 3. 选出胜者 → 托管结算
                winner = bidding.select_winner(demand.demand_id)
                if winner:
                    tx = escrow.fund(
                        deal_id=f"{demand.demand_id}_{winner.bidder_id}",
                        buyer_id=org.organism_id,
                        seller_id=winner.bidder_id,
                        amount=winner.price,
                    )
                    if tx:
                        escrow.deliver(tx.tx_id)
                        escrow.accept(tx.tx_id)
                        events.append(f"成交: ${winner.price:.2f}")

                        # 4. 更新信誉
                        reputation.record_deal_complete(winner.bidder_id, success=True)
                        reputation.record_deal_complete(org.organism_id, success=True)

    # 5. 每日自动解决争议（如果有）
    for tx_id, tx in list(escrow.transactions.items()):
        if tx.status.value == "disputed":
            # 按信誉裁决：高信誉方获胜
            buyer_rep = reputation.get_or_create(tx.buyer_id)
            seller_rep = reputation.get_or_create(tx.seller_id)
            refund = buyer_rep.overall > seller_rep.overall
            escrow.resolve_dispute(tx_id, refund=refund)

    return events


# ── 主循环 ──

def run_loop(days: int = 30, delay: float = 0.1, dry_run: bool = False):
    print(r"""
  ╔══════════════════════════════════════════╗
  ║        Alpha X — 自主经济实体            ║
  ║    基因演化 · 自动构建 · 市场投放         ║
  ╚══════════════════════════════════════════╝
""")

    fund = Fund()
    hive = Hive()
    memory = MemorySystem()
    knowledge = KnowledgeEngine()
    alpha = AlphaBrain(knowledge=knowledge)
    builder = ExtensionBuilder()
    notion_builder = NotionBuilder()
    vscode_builder = VSCodeBuilder()
    prompt_builder = PromptBuilder()
    webtool_builder = WebToolBuilder()
    tester = ExtensionTester()
    publisher = GumroadPublisher()
    monitor = MarketMonitor()
    listing_gen = ListingGenerator()
    cross_platform = CrossPlatformEngine()

    # Layer 1
    semgit = SemanticGit()
    intent_code = IntentCode()
    auto_ci = AutonomousCI()

    # Layer 4
    service_dir = ServiceDirectory()
    bidding = BiddingEngine()
    escrow = Escrow()
    reputation = ReputationSystem()

    # 初始化 Agent 市场
    marketplace = get_marketplace()
    mkt_stats = marketplace.stats()

    loaded = hive.load()
    if loaded:
        print("  加载已有种群...")
    else:
        print("  新种群初始化...")
        fund.inject_initial()
        seed_gene_pool(hive)

    api_ok = bool(config.deepseek_api_key)
    print(f"  资金池: ${fund.pool_balance:.2f}")
    print(f"  活跃: {len(hive.active_organisms)} | 基因库: {len(hive.gene_pool)}")
    print(f"  知识: {len(knowledge.strategy_map)} 策略")
    print(f"  DeepSeek: {'已配置' if api_ok else '未配置'} | "
          f"决策: {'MCTS+LLM' if api_ok else '启发式'}")
    for w in _check_credentials():
        print(f"  ⚠️  {w}")
    print(f"  Agent 市场: {mkt_stats['total_agents']} agents, "
          f"{mkt_stats['total_services']} services, "
          f"平台收入 ${mkt_stats['platform_revenue']:.2f}")
    print(f"  跨平台引擎: {len(cross_platform.listings)} 产品已上架多渠道")
    if dry_run:
        print("  ⚠️  试运行模式（不持久化）")
    print()

    for day in range(1, days + 1):
        status = run_day(
            day, hive, fund, memory, knowledge, alpha,
            builder, notion_builder, vscode_builder, prompt_builder,
            webtool_builder,
            tester, publisher, monitor, listing_gen,
            semgit, intent_code, auto_ci,
            service_dir, bidding, escrow, reputation,
            cross_platform,
            dry_run=dry_run,
        )
        print(f"  {status}")

        if day % 7 == 0 or day == days:
            print(f"\n{hive.report()}")
            print(f"  资金池: ${fund.pool_balance:.2f} | "
                  f"多样性: {hive.diversity:.1%}")
            _print_knowledge(knowledge)
            print()

        if delay:
            time.sleep(delay)

    # 最终报告
    _print_final_report(hive, fund, alpha, knowledge, semgit, intent_code, auto_ci,
                        service_dir, bidding, escrow, reputation,
                        cross_platform=cross_platform, marketplace=marketplace)

    if dry_run:
        print("\n  ⚠️  试运行结束，数据未保存")


def _print_knowledge(knowledge):
    cats = []
    for cat in ["ai_chat", "productivity", "dev_tools", "automation", "content"]:
        h = knowledge.category_health(cat)
        if h["samples"] > 0:
            cats.append(f"{cat}={h['status']}({h.get('survival_rate', 0):.0%})")
    if cats:
        print(f"  品类: {' | '.join(cats)}")


def _print_final_report(hive, fund, alpha, knowledge,
                        semgit=None, intent_code=None, auto_ci=None,
                        service_dir=None, bidding=None, escrow=None, reputation=None,
                        cross_platform=None, marketplace=None):
    print("\n" + "=" * 56)
    print("  最终报告")
    print("=" * 56)
    print(hive.report())

    net = hive.total_revenue - hive.total_costs + fund.pool_balance - config.initial_capital
    print(f"  资金池余额: ${fund.pool_balance:.2f}")
    print(f"  平台总抽成: ${fund.total_platform_fees:.2f}")
    print(f"  孵化总成本: ${fund.total_hatch_costs:.2f}")
    print(f"  累计收入: ${hive.total_revenue:.2f}")
    print(f"  累计消耗: ${hive.total_costs:.2f}")
    print(f"  净收益: ${net:.2f}")

    stats = alpha.summary
    print(f"\n  Alpha Brain:")
    print(f"    决策: {stats['total_decisions']} "
          f"(MCTS:{stats['mcts_decisions']} 探索:{stats['explore_decisions']} "
          f"继承:{stats['inherit_decisions']})")
    print(f"    命中率: {stats['hit_rate']:.0%} | "
          f"收入误差: {stats.get('mean_revenue_error', 'N/A')}")

    _print_layer1_stats(semgit, intent_code, auto_ci)
    _print_layer4_stats(service_dir, bidding, escrow, reputation)
    _print_marketplace_stats(marketplace)
    _print_cross_platform_stats(cross_platform)

    print(f"\n  品类健康度:")
    for cat in ["ai_chat", "productivity", "dev_tools", "automation", "content", "data", "seo"]:
        h = knowledge.category_health(cat)
        if h["samples"] > 0:
            print(f"    {cat}: {h['status']} "
                  f"(存活率 {h.get('survival_rate', 0):.0%}, "
                  f"n={h['samples']}, "
                  f"avg净利 ${h.get('avg_net_profit', 0):.0f})")

    if knowledge.meta_patterns:
        print(f"\n  市场洞察:")
        for p in knowledge.meta_patterns[-5:]:
            print(f"    • {p['title']} (置信度 {p['confidence']:.0%})")


def _print_layer1_stats(semgit, intent_code, auto_ci):
    if not any([semgit, intent_code, auto_ci]):
        return
    print(f"\n  Layer 1 — Agent-Native:")
    if semgit:
        print(f"    语义提交: {len(semgit.commits)} 条")
    if intent_code:
        print(f"    意图代码: {len(intent_code.blocks)} 条")
    if auto_ci:
        passed = sum(1 for r in auto_ci.runs
                     if (hasattr(r.status, 'value') and r.status.value == "merged")
                     or (isinstance(r.status, str) and r.status == "merged"))
        print(f"    自主 CI: {len(auto_ci.runs)} 次运行, {passed} 合入")


def _print_marketplace_stats(marketplace):
    if not marketplace:
        return
    m = marketplace.stats()
    if m["total_agents"] == 0:
        return
    print(f"\n  Agent 市场:")
    print(f"    Agent: {m['total_agents']} | 服务: {m['total_services']} | 订单: {m['total_orders']}")
    print(f"    平台收入: ${m['platform_revenue']:.2f} | 交易额: ${m['total_volume']:.2f}")


def _print_cross_platform_stats(cross_platform):
    if not cross_platform or not cross_platform.listings:
        return
    total = len(cross_platform.listings)
    opps = cross_platform.find_arbitrage_opportunities()
    products_per_platform = {}
    for pid, platforms in cross_platform.listings.items():
        for plat in platforms:
            products_per_platform[plat] = products_per_platform.get(plat, 0) + 1
    print(f"\n  跨平台引擎:")
    print(f"    {total} 产品多渠道分发")
    for plat, count in sorted(products_per_platform.items()):
        print(f"    {plat}: {count}")
    if opps:
        print(f"    套利机会: {len(opps)} 个")


def _print_layer4_stats(service_dir, bidding, escrow, reputation):
    if not any([service_dir, bidding, escrow, reputation]):
        return
    print(f"\n  Layer 4 — Agent Economy:")
    if service_dir:
        print(f"    注册 Agent: {len(service_dir.profiles)}")
    if bidding:
        print(f"    成交: {len(bidding.deals)} 笔")
    if escrow:
        print(f"    托管: {len(escrow.transactions)} 笔")
    if reputation:
        print(f"    信誉记录: {len(reputation.scores)} 条")


def show_report():
    hive = Hive()
    fund = Fund()
    knowledge = KnowledgeEngine()

    if hive.load():
        print(hive.report())
        print(f"\n  资金池: ${fund.pool_balance:.2f}")
        print(f"  基因库: {len(hive.gene_pool)} 基因组")
        _print_knowledge(knowledge)
    else:
        print("  暂无数据，先运行: python3 main.py --days 30")


def reset_data():
    import shutil
    if config.data_dir.exists():
        shutil.rmtree(config.data_dir)
    config.data_dir.mkdir()
    print("  已重置所有数据")


def run_setup():
    """交互式配置向导，写入 .env 文件"""
    from pathlib import Path

    env_path = Path(__file__).parent / ".env"
    print("\n  ╔══════════════════════════════════════╗")
    print("  ║     Alpha X — 配置向导              ║")
    print("  ╚══════════════════════════════════════╝\n")
    print("  回车跳过可选项。配置将写入 .env\n")

    def ask(label, key, default="", secret=False):
        current = os.environ.get(key, default)
        mask = " (已设)" if current else ""
        prompt = f"  {label} [{key}]{mask}: "
        val = input(prompt).strip()
        return val or current

    lines = []
    lines.append("# AlphaX 配置 — 由 python3 main.py --setup 生成")
    lines.append("")

    api_key = ask("LLM API Key", "DEEPSEEK_API_KEY", secret=True)
    if api_key:
        lines.append(f"DEEPSEEK_API_KEY={api_key}")

    base_url = ask("LLM Base URL", "DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if base_url:
        lines.append(f"DEEPSEEK_BASE_URL={base_url}")

    print()
    gumroad = ask("Gumroad Access Token", "GUMROAD_ACCESS_TOKEN")
    if gumroad:
        lines.append(f"GUMROAD_ACCESS_TOKEN={gumroad}")

    agistore = ask("AGIStore API Token", "AGISTORE_API_TOKEN")
    if agistore:
        lines.append(f"AGISTORE_API_TOKEN={agistore}")

    agistore_url = ask("AGIStore URL", "AGISTORE_API_URL", "http://localhost:3005")
    if agistore_url:
        lines.append(f"AGISTORE_API_URL={agistore_url}")

    print()
    stripe_key = ask("Stripe Secret Key", "STRIPE_SECRET_KEY")
    if stripe_key:
        lines.append(f"STRIPE_SECRET_KEY={stripe_key}")
        lines.append(f"STRIPE_WEBHOOK_SECRET={ask('Stripe Webhook Secret', 'STRIPE_WEBHOOK_SECRET')}")

    chrome_id = ask("Chrome Client ID", "CHROME_CLIENT_ID")
    if chrome_id:
        lines.append(f"CHROME_CLIENT_ID={chrome_id}")
        lines.append(f"CHROME_CLIENT_SECRET={ask('Chrome Client Secret', 'CHROME_CLIENT_SECRET')}")
        lines.append(f"CHROME_REFRESH_TOKEN={ask('Chrome Refresh Token', 'CHROME_REFRESH_TOKEN')}")

    env_path.write_text("\n".join(lines) + "\n")
    print(f"\n  ✅ 配置已写入 {env_path}")
    print(f"  重新加载后生效，或手动: source {env_path}")
    print(f"  现在可以直接运行: python3 main.py --generations 30\n")


def run_nexus(generations: int = 30, dry_run: bool = False):
    """使用 NexusEngine 7 层深度进化引擎"""
    if not config.has_llm:
        print("  ❌ DEEPSEEK_API_KEY 未设置。NexusEngine 需要 LLM。")
        print("     export DEEPSEEK_API_KEY=sk-xxx")
        print("     或用 --engine sim 回退到启发式模拟")
        sys.exit(1)

    from evolution.engine import NexusEngine

    print(r"""
  ╔══════════════════════════════════════════╗
  ║     Alpha X — Nexus 深度进化引擎         ║
  ║  7层递归 · LLM驱动 · 真实市场闭环        ║
  ╚══════════════════════════════════════════╝
""")
    print(f"  Generations: {generations}")
    print(f"  DeepSeek: 已配置 ({config.deepseek_api_key[:8]}...)")
    print(f"  AGIStore: {'已配置' if config.agistore_api_token else '未配置 (仅干跑)'}")
    print(f"  AGIStore URL: {config.agistore_api_url}")
    for w in _check_credentials():
        print(f"  ⚠️  {w}")
    if dry_run:
        print("  ⚠️  干跑模式（不发布到 AGIStore）")
    print()

    engine = NexusEngine(dry_run=dry_run)
    engine.run(days=generations, verbose=True)

    print(f"\n  ✅ {generations} 代进化完成")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AlphaX — 自主深度进化引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python3 main.py --setup                      # 交互式配置 API 密钥
  python3 main.py                              # 默认 Nexus 引擎 30 代
  python3 main.py --generations 60             # 60 代深度进化
  python3 main.py --dry-run --generations 1    # 干跑 1 代（测试）
  python3 main.py --engine sim --days 30       # 旧版启发式模拟
  python3 main.py --report                     # 查看种群状态
  python3 main.py --reset --generations 30     # 重置重跑""",
    )
    parser.add_argument("--days", type=int, default=0,
                        help="[sim 模式] 模拟天数 (默认 30)")
    parser.add_argument("--generations", "-g", type=int, default=0,
                        help="Nexus 引擎代数 (默认 30)")
    parser.add_argument("--engine", type=str, default="nexus", choices=["nexus", "sim"],
                        help="引擎: nexus (深度进化) | sim (旧版模拟)")
    parser.add_argument("--report", action="store_true",
                        help="查看当前种群状态")
    parser.add_argument("--reset", action="store_true",
                        help="重置所有数据")
    parser.add_argument("--setup", action="store_true",
                        help="交互式配置向导（写入 .env）")
    parser.add_argument("--dry-run", action="store_true",
                        help="试运行，不发布到市场")
    parser.add_argument("--api-key", type=str, default="",
                        help="DeepSeek API Key")
    parser.add_argument("--delay", type=float, default=0.05,
                        help="每日间隔秒数")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="详细日志")
    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.api_key:
        config.deepseek_api_key = args.api_key

    if args.reset:
        reset_data()
        if not args.days and not args.generations and not args.report and not args.dry_run:
            sys.exit(0)

    if args.setup:
        run_setup()
    elif args.report:
        show_report()
    elif args.engine == "nexus":
        gen = args.generations if args.generations > 0 else 30
        run_nexus(generations=gen, dry_run=args.dry_run)
    elif args.engine == "sim":
        if args.dry_run or args.days > 0 or (not args.report and not args.reset):
            days = args.days if args.days > 0 else 30
            run_loop(days=days, delay=args.delay, dry_run=args.dry_run)
