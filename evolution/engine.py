"""七层递归自改进进化引擎 + 六维深度进化

主循环: observe → reflect → mutate → create → critique → execute → validate → compete → deploy → feedback

Layer 1: 产物进化 (Creator 多LLM生成 + Prompt自我进化)
Layer 2: 策略进化 (DynamicGenome + 竞争动力学)
Layer 3: 元规则进化 (Mutator 改自身 config)
Layer 4: 价值体系进化 (Reflector + MetaReflector 二阶学习)
Layer 5: 对抗自博弈 (Creator vs LLM Critic + 真实执行验证)
Layer 6: 工具创生 (Toolkit 自写工具注册)
Layer 7: 基因交换 (GeneBank 跨实例基因池)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class DayStats:
    day: int
    active: int
    deaths: int
    breeds: int
    hatches: int
    builds_generated: int
    builds_passed: int
    builds_executed: int       # 真实执行通过的
    insights_found: int
    mutations_applied: int
    prompts_evolved: int       # prompt 进化次数
    niches_active: int         # 活跃竞争 niche 数
    trends_found: int          # 趋势信号数
    assets_generated: int      # 营销资产生成数
    gumroad_deployed: int      # Gumroad 真实上架数
    agistore_deployed: int    # AGIStore 真实上架数
    total_revenue: float
    total_cost: float
    fund_balance: float
    pool_diversity: float
    meta_effectiveness: float  # 二阶学习有效比例


@dataclass
class NexusEngine:
    """七层递归自改进进化引擎 + 六维深度进化"""

    dry_run: bool = False  # True = 不发布到市场

    # 核心组件（延迟初始化）
    gene_pool: object = None
    chamber: object = None
    env: object = None
    fossil_db: object = None
    toolkit: object = None
    gene_bank: object = None

    # Brain 层
    observer: object = None
    reflector: object = None
    meta_reflector: object = None
    mutator: object = None
    creator: object = None
    critic: object = None
    prompt_evolver: object = None

    # 执行 + 竞争 + 市场
    executor: object = None
    validator: object = None
    competition: object = None
    trend_engine: object = None
    gumroad: object = None
    agistore: object = None
    marketing: object = None

    # 自主深度学习
    pricing_learner: object = None
    cross_learner: object = None
    product_iterator: object = None
    screenshot_gen: object = None

    # 信誉 + 组合 + 竞品 + 进化链
    proof_engine: object = None
    bundle_engine: object = None
    competitor_radar: object = None
    evolution_chain: object = None

    # 状态
    history: list[DayStats] = field(default_factory=list)
    current_day: int = 0
    _started_at: str = ""

    def __post_init__(self):
        self._init_components()

    def _init_components(self):
        """延迟初始化所有组件"""
        # 核心进化组件
        from evolution.genepool import GenePool
        from evolution.chamber import BreedingChamber
        from evolution.environment import SimulatedEnvironment, GumroadEnvironment

        self.gene_pool = GenePool()
        self.chamber = BreedingChamber()
        if config.gumroad_access_token:
            self.env = GumroadEnvironment(access_token=config.gumroad_access_token)
        else:
            self.env = SimulatedEnvironment()

        # Memory 层
        from brain.fossil import FossilDB
        from memory.toolkit import Toolkit
        from memory.gene_bank import GeneBank

        self.fossil_db = FossilDB()
        self.toolkit = Toolkit()
        self.gene_bank = GeneBank()

        # Brain 层
        from brain.observer import Observer
        from brain.reflector import Reflector
        from brain.meta_reflector import MetaReflector
        from brain.mutator import Mutator
        from brain.creator import Creator
        from brain.critic import Critic
        from brain.prompt_evolver import PromptEvolver

        self.observer = Observer()
        self.reflector = Reflector()
        self.meta_reflector = MetaReflector()
        self.mutator = Mutator()
        self.creator = Creator()
        self.critic = Critic()
        self.prompt_evolver = PromptEvolver()

        # 执行 + 验证 + 竞争 + 市场
        from env.executor import Executor
        from env.validator import Validator
        from core.competition import CompetitionEngine
        from env.trend_arbitrage import TrendArbitrageEngine
        from env.gumroad_deploy import GumroadDeployer
        from env.agistore_deploy import AGIStoreDeployer
        from env.marketing import MarketingEngine

        self.executor = Executor()
        self.validator = Validator()
        self.competition = CompetitionEngine()
        self.trend_engine = TrendArbitrageEngine()
        self.gumroad = GumroadDeployer()
        self.agistore = AGIStoreDeployer()
        self.marketing = MarketingEngine()

        # 自主学习模块
        from brain.pricing_learner import PricingLearner
        from brain.cross_learner import CrossLearner
        from env.product_iterator import ProductIterator
        from env.screenshot import ScreenshotGenerator

        self.pricing_learner = PricingLearner()
        self.cross_learner = CrossLearner()
        self.product_iterator = ProductIterator()
        self.screenshot_gen = ScreenshotGenerator()

        # 信誉 + 组合 + 竞品 + 进化链
        from brain.proof_engine import ProofEngine
        from brain.bundle_engine import BundleEngine
        from env.competitor_radar import CompetitorRadar
        from brain.evolution_chain import EvolutionChainLogger

        self.proof_engine = ProofEngine()
        self.bundle_engine = BundleEngine()
        self.competitor_radar = CompetitorRadar()
        self.evolution_chain = EvolutionChainLogger()

    # ── 主循环 ──

    def run(self, days: int, verbose: bool = True) -> list[DayStats]:
        """运行进化主循环 N 天"""
        self._started_at = datetime.now(timezone.utc).isoformat()

        if verbose:
            active = self.chamber.hive.active_organisms
            print(f"\n{'═' * 70}")
            print(f"  Nexus Engine — 7 Layers + 6 Deep Evolution Dimensions")
            print(f"  Days: {days} | Capital: ${self.chamber.fund.pool_balance:.0f}")
            print(f"  Gene pool: {len(self.gene_pool.gene_pool)} genomes")
            print(f"  Active organisms: {len(active)} | Fossils: {self.fossil_db.count}")
            print(f"  Depth: LLM Critic + Executor + Competition + Meta-Learning + PromptEvolve")
            print(f"{'═' * 70}\n")

        for _ in range(days):
            self.current_day += 1
            stats = self._tick_day(verbose)
            self.history.append(stats)

            if verbose and self.current_day % 5 == 0:
                self._print_stats(stats)

            time.sleep(0.05)

        # ── 运行结束：评估二阶学习效果 ──
        if self.meta_reflector:
            matured = self.meta_reflector.evaluate(self._avg_fitness())
            if matured and verbose:
                print(f"\n  Meta-Learning: {len(matured)} insights matured")
                best_types = self.meta_reflector.best_insight_types[:2]
                for itype, avg, count in best_types:
                    print(f"    Most effective: {itype} (+{avg:.3f} fitness, n={count})")

        if verbose:
            self._print_summary()
        return self.history

    # ── 单日循环（全部 6 个深度维度） ──

    def _tick_day(self, verbose: bool) -> DayStats:
        hatches, deaths, breeds = 0, 0, 0
        builds_generated, builds_passed, builds_executed = 0, 0, 0
        insights_found, mutations_applied = 0, 0
        prompts_evolved = 0
        assets_generated = 0
        gumroad_deployed = 0
        agistore_deployed = 0

        # ═══════════════════════════════════════════
        # Phase 1: 观察（拓宽数据源：GitHub + PH + Chrome Store）
        # ═══════════════════════════════════════════
        population = self._get_population_snapshot()
        obs_log = self.observer.scan(population)
        market_signal_count = len(obs_log.market_signals) if obs_log else 0

        # ── 趋势套利扫描 ──
        trend_report = self.trend_engine.scan(
            fossils=self.fossil_db.recent_losses,
            organisms=self.chamber.hive.active_organisms,
        )
        hottest_categories = self.trend_engine.hottest_categories

        # ═══════════════════════════════════════════
        # Phase 2: 反思（含二阶学习偏向）
        # ═══════════════════════════════════════════
        if self._should_reflect():
            avg_fitness = self._avg_fitness()
            gene_pool_stats = {
                "total_genomes": len(self.gene_pool.gene_pool),
                "categories": list(set(
                    g.category.value if hasattr(g.category, 'value') else str(g.category)
                    for g in self.gene_pool.gene_pool.values()
                )),
                "diversity": getattr(self.chamber, 'diversity', 0),
                "avg_fitness": avg_fitness,
            }

            insights = self.reflector.think(
                recent_logs=[obs_log] if obs_log else [],
                fossils=self.fossil_db.recent_losses,
                gene_pool_stats=gene_pool_stats,
            )
            insights_found = len(insights)

            if insights:
                # 追踪每条 insight 用于二阶学习
                for ins in insights:
                    self.meta_reflector.track(ins, avg_fitness)

                mutations = self.mutator.apply(insights, self.gene_pool)
                mutations_applied = len(mutations)

        # ═══════════════════════════════════════════
        # Phase 3: 创建 + 对抗审查 + 真实执行
        # ═══════════════════════════════════════════
        new_orgs_today = min(3, max(1, 3 if self.current_day % 5 == 0 else 1))

        for _ in range(new_orgs_today):
            market = self.env.market_context()
            # 用趋势套利数据增强市场上下文
            trend_context = {
                "category_health": getattr(market, 'category_health', {}),
                "trending": getattr(market, 'trending_categories', []),
            }
            for cat, score in hottest_categories[:5]:
                if cat not in trend_context["trending"]:
                    trend_context["trending"].append(cat)
                trend_context["category_health"][cat] = trend_context["category_health"].get(cat, {})
                trend_context["category_health"][cat]["arbitrage_score"] = score

            genome = self.gene_pool.select_genome(
                self.chamber.fund.pool_balance,
                market_context=trend_context,
            )

            # ── 跨产品学习偏向 ──
            cat_str = str(getattr(genome, 'category', 'dev_tools'))
            biases = self.cross_learner.get_genome_biases(cat_str)
            if biases.get("product_type") and hasattr(genome, 'product_type'):
                genome.product_type = type(genome.product_type)(biases["product_type"]) \
                    if hasattr(type(genome.product_type), '__call__') else biases["product_type"]
            if biases.get("target_audience") and hasattr(genome, 'target_audience'):
                genome.target_audience = type(genome.target_audience)(biases["target_audience"]) \
                    if hasattr(type(genome.target_audience), '__call__') else biases["target_audience"]
            if biases.get("design_style") and hasattr(genome, 'design_style'):
                genome.design_style = type(genome.design_style)(biases["design_style"]) \
                    if hasattr(type(genome.design_style), '__call__') else biases["design_style"]

            # ── 自动定价学习 ──
            new_price = self.pricing_learner.nudge_genome_price(genome, cat_str)
            if new_price:
                genome.price_point = new_price
            else:
                genome.price_point = self.pricing_learner.suggest_price(
                    cat_str, getattr(genome, 'price_point', 4.99)
                )

            # 使用 PromptEvolver 的最佳 prompt 生成
            if self.prompt_evolver and hasattr(genome, 'llm_backend'):
                prompt_id = getattr(genome, 'prompt_strategy', 'default')
                evolved_prompt = self.prompt_evolver.get_prompt(prompt_id, genome)
            else:
                evolved_prompt = ""

            # ── 生成代码 ──
            org = self.chamber.hatch(genome)
            if not org:
                continue
            hatches += 1

            build = self.creator.generate(org, strategy=evolved_prompt)
            builds_generated += 1

            # ── 对抗审查（LLM 深度审查）──
            review = self.critic.review(build)
            retry_count = 0
            while self.critic.should_retry(review, retry_count) and retry_count < 3:
                retry_count += 1
                feedback = self.critic.improvement_feedback(review)
                build = self.creator.generate(org, strategy=feedback)
                review = self.critic.review(build)

            # 记录 prompt 效果
            if self.prompt_evolver and hasattr(genome, 'prompt_strategy'):
                self.prompt_evolver.record_result(
                    getattr(genome, 'prompt_strategy', 'default'),
                    review.score,
                )

            # ── 真实执行验证 ──
            exec_report = self.executor.execute(build)
            if exec_report.success:
                builds_executed += 1
            elif exec_report.errors:
                continue  # 不能真正运行，跳过

            # ── 基本验证 ──
            val_result = self.validator.validate(build)
            if val_result.status.value == "fail":
                continue
            builds_passed += 1

            # ── 信誉证明 ──
            proof = self.proof_engine.verify(org, build)

            # ── 进化链: 记录诞生 ──
            cat_str = str(getattr(genome, 'category', 'dev_tools'))
            self.evolution_chain.record_created(
                org.organism_id,
                str(genome.express() if hasattr(genome, 'express') else f"Product {org.organism_id[:8]}"),
                cat_str,
                {"price_point": getattr(genome, 'price_point', 4.99),
                 "product_type": str(getattr(genome, 'product_type', 'web_tool')),
                 "target_audience": str(getattr(genome, 'target_audience', 'developers')),
                 "generation": getattr(genome, 'generation', 1)},
            )

            # ── 注册到竞争 niche ──
            self.competition.register(org)

            # ── 营销资产生成 ──
            marketing_assets = self.marketing.generate_assets(org, build)
            if marketing_assets:
                assets_generated += 1
                seo = self.marketing.evaluate_seo(
                    marketing_assets,
                    str(getattr(genome, 'product_type', 'web_tool')),
                    str(getattr(genome, 'category', 'dev_tools')),
                )

            # ── AGIStore 部署（优先） ──
            if not self.dry_run and self.agistore.is_available:
                deploy_result = self.agistore.deploy(org, build, marketing_assets)
                if deploy_result.success:
                    org.agistore_skill_id = deploy_result.skill_id
                    agistore_deployed += 1
                    cover = self.screenshot_gen.generate(org, build)
                    self.evolution_chain.record_deployed(
                        org.organism_id,
                        deploy_result.agistore_url or "agistore.dev",
                    )
                    # 反馈闭环：拉取 stats 计算 fitness
                    self._sync_fitness(org)

            # ── Gumroad 真实部署（备用） ──
            if self.gumroad.is_available:
                deploy_result = self.gumroad.deploy(org, build, marketing_assets)
                if deploy_result.success:
                    org.gumroad_product_id = deploy_result.product_id
                    gumroad_deployed += 1
                    # 进化链: 记录上架
                    self.evolution_chain.record_deployed(
                        org.organism_id,
                        deploy_result.gumroad_url or f"alphaxstore.gumroad.com",
                    )

            # ── 部署 ──
            org.deploy()
            self.env.deploy(org, "")

        # ═══════════════════════════════════════════
        # Phase 4: 每日心跳（含竞争调整 + AGIStore 数据同步）
        # ═══════════════════════════════════════════
        # 定期同步 AGIStore 真实数据（每天）
        if self.agistore.is_available:
            for org in self.chamber.hive.active_organisms:
                if getattr(org, 'agistore_skill_id', ''):
                    self._sync_fitness(org)

        tick_results: dict[str, dict] = {}
        for org in self.chamber.hive.active_organisms:
            tr = self.env.tick(org)
            # 竞争引擎调整收入/下载
            adjusted_income, adjusted_downloads = self.competition.compete_tick(
                org, tr.income, tr.downloads,
            )
            dist = self.chamber.fund.distribute_income(adjusted_income, org.organism_id)
            tick_results[org.organism_id] = {
                "income": dist.get("organism_share", adjusted_income),
                "downloads": adjusted_downloads,
                "rating": tr.rating,
                "api_cost": tr.api_cost,
            }

            # ── 定价学习: 记录展示 → 转化 ──
            if hasattr(org, 'genome') and org.genome:
                cat = str(getattr(org.genome, 'category', 'dev_tools'))
                price = getattr(org.genome, 'price_point', 4.99)
                downloads = adjusted_downloads
                income = adjusted_income
                self.pricing_learner.record_impression(cat, price)
                if income > 0:
                    self.pricing_learner.record_purchase(cat, price, int(income * 100))
                    self.cross_learner.record_win(org.genome, sales_count=max(1, downloads), source="internal")
                    # 进化链: 记录销售
                    self.evolution_chain.record_sale(org.organism_id, income)
                    # 捆绑引擎: 记录购买的产品
                    gid = getattr(org, 'gumroad_product_id', '')
                    if gid:
                        self.bundle_engine.record_purchase([gid])

                # 捆绑引擎: 记录浏览
                gid = getattr(org, 'gumroad_product_id', '')
                if gid:
                    self.bundle_engine.record_view([gid])

            # 竞争压力加速死亡
            if self.competition.accelerate_death(org):
                org.energy = 0  # 直接淘汰

        # ═══════════════════════════════════════════
        # Phase 5: 生死事件 + 化石 + 基因池学习
        # ═══════════════════════════════════════════
        events = self.chamber.tick_all(tick_results)
        for evt in events:
            if evt.event_type == "death":
                deaths += 1
                org = self.chamber.hive.organisms.get(evt.organism_id)
                if org:
                    self.fossil_db.bury(org)
                    self.competition.unregister(org)
                    # 进化链: 记录死亡
                    self.evolution_chain.record_death(
                        org.organism_id,
                        f"存活 {org.days_alive} 天, 收入 ${org.total_earned:.2f}, 烧掉 ${org.total_burned:.2f}",
                    )
                    if org.genome:
                        self.gene_pool.record_outcome(
                            genome=org.genome,
                            survived=False,
                            total_earned=org.total_earned,
                            total_burned=org.total_burned,
                            days_alive=org.days_alive,
                        )

        # ═══════════════════════════════════════════
        # Phase 6: 繁殖 + 基因导出
        # ═══════════════════════════════════════════
        children = self.chamber.breed_top(3)
        breeds += len(children)

        for org in self.chamber.hive.active_organisms:
            if org.can_breed and org.total_earned > org.total_burned:
                self.gene_bank.export_gene(org)

        # ── 产品自我迭代：优化表现差的产品（每 3 天）──
        improvements = []
        if self.current_day % 3 == 0 and self.product_iterator:
            improvements = self.product_iterator.scan_and_improve()
            # 进化链: 记录迭代
            for imp in improvements:
                self.evolution_chain.record_iteration(
                    imp["product_id"], imp["old_title"], imp["new_title"], "auto-optimize"
                )

        # ── 定价学习：更新最优价 ──
        self.pricing_learner.update_best_prices()

        # ── 竞品雷达扫描（每 5 天）──
        if self.current_day % 5 == 0 and self.competitor_radar:
            for cat, _, _ in self.cross_learner.top_categories()[:3]:
                self.competitor_radar.scan_category(cat)

        # ── 捆绑建议生成（每 7 天）──
        if self.current_day % 7 == 0 and self.bundle_engine:
            all_products = [
                {"id": getattr(o, 'gumroad_product_id', o.organism_id),
                 "name": str(o.genome.express() if o.genome and hasattr(o.genome, 'express') else o.organism_id[:8]),
                 "price_cents": int(getattr(o.genome, 'price_point', 4.99) * 100)}
                for o in self.chamber.hive.active_organisms
            ]
            self.bundle_engine.suggest_bundles(all_products)

        # ═══════════════════════════════════════════
        # Phase 7: Prompt 进化（每 10 天）
        # ═══════════════════════════════════════════
        if self.current_day % 10 == 0 and self.prompt_evolver:
            best = [p.prompt_id for p in self.prompt_evolver.best_prompts[:3]]
            worst = []
            all_prompts = list(self.prompt_evolver.prompt_pool.values())
            all_prompts.sort(key=lambda p: p.avg_build_quality)
            worst = [p.prompt_id for p in all_prompts[:2]]
            if best and worst:
                evo_result = self.prompt_evolver.evolve(best, worst)
                if evo_result:
                    prompts_evolved += 1

        # ═══════════════════════════════════════════
        # Phase 8: 统计
        # ═══════════════════════════════════════════
        active_orgs = self.chamber.hive.active_organisms
        total_rev = sum(o.total_earned for o in active_orgs)
        total_cost = sum(o.total_burned for o in active_orgs)

        return DayStats(
            day=self.current_day,
            active=len(active_orgs),
            deaths=deaths,
            breeds=breeds,
            hatches=hatches,
            builds_generated=builds_generated,
            builds_passed=builds_passed,
            builds_executed=builds_executed,
            insights_found=insights_found,
            mutations_applied=mutations_applied,
            prompts_evolved=prompts_evolved,
            niches_active=len(self.competition.niches),
            trends_found=len(trend_report.signals) if trend_report else 0,
            assets_generated=assets_generated,
            gumroad_deployed=gumroad_deployed,
            agistore_deployed=agistore_deployed,
            total_revenue=round(total_rev, 2),
            total_cost=round(total_cost, 2),
            fund_balance=round(self.chamber.fund.pool_balance, 2),
            pool_diversity=round(getattr(self.chamber, 'diversity', 0), 3),
            meta_effectiveness=self.meta_reflector.summary["overall_effectiveness"],
        )

    # ── 辅助 ──

    def _should_reflect(self) -> bool:
        return (
            self.current_day == 1
            or self.current_day % 7 == 0
            or (self.current_day % 3 == 0 and bool(config.deepseek_api_key))
        )

    def _avg_fitness(self) -> float:
        active = self.chamber.hive.active_organisms
        if not active:
            return 0.0
        scores = []
        for org in active:
            if org.genome:
                scores.append(org.genome.fitness_score)
        return sum(scores) / len(scores) if scores else 0.0

    def _sync_fitness(self, org) -> float:
        """从 AGIStore 拉取真实数据，计算 fitness 并写回 organism"""
        from core.fitness import compute_fitness_from_stats

        sid = getattr(org, 'agistore_skill_id', '')
        if not sid or not self.agistore.is_available:
            return 0.0

        stats = self.agistore.fetch_stats(skill_id=sid, origin_id=org.organism_id)
        if not stats:
            return 0.0

        fitness = compute_fitness_from_stats(stats)
        org.market_fitness = fitness

        # 回写到 genome，影响后续繁殖决策
        if org.genome:
            prev = org.genome.fitness_score
            org.genome.fitness_score = fitness
            from core.fitness import fitness_delta
            org.genome.fitness_trend = fitness_delta(fitness, prev)

        return fitness

    def _get_population_snapshot(self) -> list[dict]:
        snap = []
        for org in self.chamber.hive.active_organisms:
            snap.append({
                "organism_id": org.organism_id,
                "state": org.state.value if hasattr(org.state, 'value') else str(org.state),
                "energy": org.energy,
                "days_alive": org.days_alive,
                "total_earned": org.total_earned,
                "total_burned": org.total_burned,
                "total_downloads": org.total_downloads,
                "genome_summary": org.genome.express() if org.genome and hasattr(org.genome, 'express') else "unknown",
            })
        return snap

    # ── 输出 ──

    def _print_stats(self, s: DayStats):
        net = s.total_revenue - s.total_cost
        print(f"  day {s.day:>4d} │ active={s.active:<3d} hatch={s.hatches} "
              f"died={s.deaths} bred={s.breeds} │ "
              f"builds={s.builds_executed}/{s.builds_passed}/{s.builds_generated} "
              f"insights={s.insights_found} │ "
              f"trends={s.trends_found} mktg={s.assets_generated} gum={s.gumroad_deployed} │ "
              f"rev=${s.total_revenue:>6.0f} net=${net:>6.0f} fund=${s.fund_balance:>6.0f}")

    def _print_summary(self):
        if not self.history:
            return
        h = self.history
        total_deaths = sum(s.deaths for s in h)
        total_breeds = sum(s.breeds for s in h)
        total_hatches = sum(s.hatches for s in h)
        total_builds = sum(s.builds_generated for s in h)
        total_passed = sum(s.builds_passed for s in h)
        total_executed = sum(s.builds_executed for s in h)
        total_insights = sum(s.insights_found for s in h)
        total_p_evolved = sum(s.prompts_evolved for s in h)
        total_trends = sum(s.trends_found for s in h)
        total_assets = sum(s.assets_generated for s in h)
        final = h[-1]

        print(f"\n{'─' * 70}")
        print(f"  Nexus Deep Evolution complete — {self.current_day} days")
        print(f"  Hatched: {total_hatches} │ Died: {total_deaths} │ Bred: {total_breeds}")
        print(f"  Builds: {total_executed} executed / {total_passed} passed / {total_builds} generated")
        print(f"  Insights: {total_insights} │ Prompts evolved: {total_p_evolved}")
        print(f"  Trends found: {total_trends} │ Marketing assets: {total_assets}")
        print(f"  Surviving: {final.active} │ Fund: ${final.fund_balance:.0f}")
        print(f"  Competition: {self.competition.summary}")
        print(f"  Trend: {self.trend_engine.summary}")
        print(f"  Marketing: {self.marketing.summary}")
        print(f"  Gumroad: {self.gumroad.summary}")
        print(f"  AGIStore: {self.agistore.summary}")
        print(f"  Pricing: {self.pricing_learner.summary}")
        print(f"  Cross-learn: {self.cross_learner.summary}")
        print(f"  Product Iter: {self.product_iterator.summary}")
        print(f"  Covers: {self.screenshot_gen.summary}")
        print(f"  Proof: {self.proof_engine.summary}")
        print(f"  Bundles: {self.bundle_engine.summary}")
        print(f"  Radar: {self.competitor_radar.summary}")
        print(f"  EvoChain: {self.evolution_chain.summary}")
        print(f"{'─' * 70}")

    @property
    def status(self) -> dict:
        active = self.chamber.hive.active_organisms
        return {
            "day": self.current_day,
            "started_at": self._started_at,
            "active_organisms": len(active),
            "gene_pool_size": len(self.gene_pool.gene_pool),
            "fossil_count": self.fossil_db.count,
            "tool_count": self.toolkit.summary["total_tools"],
            "prompt_pool_size": len(self.prompt_evolver.prompt_pool),
            "gene_bank": self.gene_bank.summary,
            "competition": self.competition.summary,
            "trends": self.trend_engine.summary,
            "marketing": self.marketing.summary,
            "gumroad": self.gumroad.summary,
            "agistore": self.agistore.summary,
            "pricing": self.pricing_learner.summary,
            "cross_learn": self.cross_learner.summary,
            "product_iter": self.product_iterator.summary,
            "screenshots": self.screenshot_gen.summary,
            "proof": self.proof_engine.summary,
            "bundles": self.bundle_engine.summary,
            "radar": self.competitor_radar.summary,
            "evo_chain": self.evolution_chain.summary,
            "meta_learning": self.meta_reflector.summary,
            "fund_balance": round(self.chamber.fund.pool_balance, 2),
            "total_revenue": round(sum(o.total_earned for o in active), 2),
        }
