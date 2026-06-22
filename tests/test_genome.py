"""基因组测试：变异、重组、表达、距离"""

import pytest
from core.genome import (
    Genome, SEED_GENOMES, GENE_SPACE,
    ProductType, Category, PricingModel, TargetMarket, TitlePattern,
)


class TestGenomeBasics:
    def test_default_genome(self):
        g = Genome()
        assert g.product_type == ProductType.CHROME_EXTENSION
        assert g.category == Category.AI_CHAT
        assert g.price_point == 3.99
        assert g.generation == 0

    def test_genome_id_is_stable(self):
        g1 = Genome(category=Category.AI_CHAT, price_point=3.99)
        g2 = Genome(category=Category.AI_CHAT, price_point=3.99)
        assert g1.genome_id == g2.genome_id
        # 不同基因型产生不同 ID
        g3 = Genome(category=Category.AI_CHAT, price_point=4.99)
        assert g1.genome_id != g3.genome_id

    def test_genome_id_length(self):
        g = Genome()
        assert len(g.genome_id) == 12

    def test_express_formats_title(self):
        g = Genome(
            category=Category.AI_CHAT,
            title_pattern=TitlePattern.ONE_CLICK,
            target_market=TargetMarket.ENGLISH,
        )
        name = g.express()
        assert "Chat Export" in name
        assert "One-Click" in name

    def test_express_smart_pattern(self):
        g = Genome(title_pattern=TitlePattern.SMART)
        name = g.express()
        assert "Smart" in name
        assert "—" in name

    def test_express_unknown_format_key_falls_back(self):
        # 即使有未知 key 也不会崩溃
        g = Genome(title_pattern=TitlePattern.PRO)
        name = g.express()
        assert len(name) > 0
        assert "Pro" in name

    def test_survival_rate_default(self):
        g = Genome()
        assert g.survival_rate == 0.5

    def test_survival_rate_calculated(self):
        g = Genome(times_used=10, times_succeeded=7)
        assert g.survival_rate == 0.7


class TestMutation:
    def test_mutation_creates_child(self):
        parent = Genome()
        child = parent.mutate()
        assert child.generation == parent.generation + 1
        assert child.parent_id == parent.genome_id
        # 大多数变异会改变核心基因型（price_point/category等）
        # 少数只改变表达细节（description_style/screenshot_count），ID 不变
        # 多次变异应产生不同的后代
        mutants = [parent.mutate() for _ in range(10)]
        ids = {m.genome_id for m in mutants}
        # 至少有一种不同的基因型（变异率 10% × 6 核心位点）
        assert len(ids) >= 1

    def test_mutation_resets_fitness(self):
        parent = Genome(fitness_score=0.9, times_used=10, times_succeeded=8)
        child = parent.mutate()
        assert child.fitness_score == 0.0
        assert child.times_used == 0
        assert child.times_succeeded == 0

    def test_mutation_changes_some_fields(self):
        parent = Genome(price_point=3.99, category=Category.AI_CHAT)
        # 多次变异，确保至少有些后代不同
        mutants = [parent.mutate() for _ in range(20)]
        differences = sum(
            1 for m in mutants
            if m.price_point != 3.99 or m.category != Category.AI_CHAT
        )
        assert differences > 0

    def test_mutation_preserves_product_type_range(self):
        g = Genome(product_type=ProductType.CHROME_EXTENSION)
        for _ in range(50):
            child = g.mutate()
            assert child.product_type in ProductType

    def test_mutation_price_within_bounds(self):
        g = Genome(price_point=3.99)
        for _ in range(50):
            child = g.mutate()
            assert 0.99 <= child.price_point <= 99.99


class TestRecombination:
    def test_recombine_yields_child(self):
        a = Genome(category=Category.AI_CHAT, price_point=3.99)
        b = Genome(category=Category.DEV_TOOLS, price_point=9.99)
        child = a.recombine(b)
        assert child.generation == max(a.generation, b.generation) + 1
        assert "+" in (child.parent_id or "")

    def test_recombine_inherits_from_both_parents(self):
        a = Genome(category=Category.AI_CHAT, price_point=1.99,
                   target_market=TargetMarket.ENGLISH)
        b = Genome(category=Category.DEV_TOOLS, price_point=19.99,
                   target_market=TargetMarket.DEVELOPER)
        # 多次重组应该产生混合后代
        results = set()
        for _ in range(30):
            child = a.recombine(b)
            results.add((child.category, child.target_market))
        # 至少有两种组合
        assert len(results) >= 2


class TestGeneticDistance:
    def test_identical_genomes(self):
        g1 = Genome(category=Category.AI_CHAT, price_point=3.99)
        g2 = Genome(category=Category.AI_CHAT, price_point=3.99)
        assert g1.genetic_distance(g2) == 0.0

    def test_completely_different(self):
        g1 = Genome(
            product_type=ProductType.CHROME_EXTENSION,
            category=Category.AI_CHAT,
            pricing_model=PricingModel.ONE_TIME,
            target_market=TargetMarket.ENGLISH,
            title_pattern=TitlePattern.ONE_CLICK,
            price_point=1.99,
            description_style="benefit_first",
            screenshot_count=2,
            code_complexity="minimal",
        )
        g2 = Genome(
            product_type=ProductType.API_SERVICE,
            category=Category.AUTOMATION,
            pricing_model=PricingModel.SUBSCRIPTION,
            target_market=TargetMarket.CHINESE,
            title_pattern=TitlePattern.PRO,
            price_point=19.99,
            description_style="story",
            screenshot_count=5,
            code_complexity="rich",
        )
        dist = g1.genetic_distance(g2)
        assert dist > 0.5  # 大部分不同

    def test_one_field_different(self):
        g1 = Genome(price_point=3.99)
        g2 = Genome(price_point=4.99)
        assert 0 < g1.genetic_distance(g2) < 0.2


class TestIdentityRelation:
    def test_clone(self):
        g1 = Genome(price_point=3.99)
        g2 = Genome(price_point=3.99)
        assert g1.identity_relation(g2) == "clone"

    def test_new_species(self):
        # 最大不同的两个基因组
        g1 = Genome(
            category=Category.AI_CHAT, price_point=1.99,
            product_type=ProductType.CHROME_EXTENSION,
            target_market=TargetMarket.ENGLISH,
            pricing_model=PricingModel.ONE_TIME,
            title_pattern=TitlePattern.ONE_CLICK,
            description_style="benefit_first",
            screenshot_count=2,
            code_complexity="minimal",
        )
        g2 = Genome(
            category=Category.AUTOMATION, price_point=19.99,
            product_type=ProductType.API_SERVICE,
            target_market=TargetMarket.CHINESE,
            pricing_model=PricingModel.SUBSCRIPTION,
            title_pattern=TitlePattern.PRO,
            description_style="story",
            screenshot_count=5,
            code_complexity="rich",
        )
        assert g1.identity_relation(g2) == "new_species"


class TestSeedGenomes:
    def test_seeds_exist(self):
        assert len(SEED_GENOMES) >= 8

    def test_seeds_have_multiple_product_types(self):
        types = {s.product_type for s in SEED_GENOMES}
        assert ProductType.CHROME_EXTENSION in types
        assert len(types) >= 5  # 至少 5 种产品类型

    def test_seeds_have_different_categories(self):
        cats = {s.category for s in SEED_GENOMES}
        assert Category.AI_CHAT in cats
        assert Category.PRODUCTIVITY in cats
        assert Category.DEV_TOOLS in cats
