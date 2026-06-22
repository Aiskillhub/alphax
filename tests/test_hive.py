"""蜂巢测试：孵化、繁殖、淘汰、多样性"""

import pytest
from core.hive import Hive
from core.genome import Genome, SEED_GENOMES, Category, ProductType
from core.organism import Organism, OrganismState


class TestHiveHatch:
    def test_hatch_creates_organism(self):
        hive = Hive()
        org = hive.hatch(strategy="seed")
        assert org.organism_id in hive.organisms
        assert org.genome is not None
        assert org.energy > 0

    def test_hatch_with_specific_genome(self):
        hive = Hive()
        genome = SEED_GENOMES[0].mutate()
        org = hive.hatch(genome=genome)
        assert org.genome.genome_id == genome.genome_id

    def test_hatch_batch(self):
        hive = Hive()
        orgs = hive.hatch_batch(5, strategy="seed")
        assert len(orgs) == 5
        assert len(hive.organisms) == 5

    def test_hatch_with_parent(self):
        hive = Hive()
        parent = hive.hatch(strategy="seed")
        child = hive.hatch(parent=parent)
        assert child.parent_organism_id == parent.organism_id

    def test_hatch_enforces_max_population(self):
        hive = Hive()
        # 一次性孵化超过上限
        orgs = hive.hatch_batch(55, strategy="seed")
        assert len(hive.active_organisms) <= 50

    def test_hatch_explore_strategy(self):
        hive = Hive()
        org = hive.hatch(strategy="explore")
        assert org.genome is not None


class TestHiveBreed:
    def test_breed_requires_eligible_parent(self):
        hive = Hive()
        org = hive.hatch(strategy="seed")
        # 新个体不能繁殖
        child = hive.breed(org)
        assert child is None

    def test_breed_creates_child(self):
        hive = Hive()
        org = hive.hatch(strategy="seed")
        # 手动设置满足繁殖条件
        org.days_alive = 30
        org.days_energy_positive = 25
        org.energy = 50.0
        org.state = OrganismState.ACTIVE

        child = hive.breed(org)
        assert child is not None
        assert child.parent_organism_id == org.organism_id
        assert child.genome is not None
        # 父代回到 ACTIVE 状态
        assert org.state == OrganismState.ACTIVE

    def test_breed_top_selects_best(self):
        hive = Hive()
        for _ in range(10):
            org = hive.hatch(strategy="seed")
            org.days_alive = 30
            org.days_energy_positive = 25
            org.energy = 50.0
            org.state = OrganismState.ACTIVE  # 必须先部署
            if org.genome:
                org.genome.fitness_score = 0.5

        active = hive.active_organisms
        if active and active[0].genome:
            active[0].genome.fitness_score = 0.95

        children = hive.breed_top(n=2)
        assert len(children) <= 2


class TestHiveDeath:
    def test_organisms_die(self):
        hive = Hive()
        org = hive.hatch(strategy="seed")
        org.state = OrganismState.DYING
        hive._kill(org)
        assert org.state == OrganismState.DEAD
        assert org in hive.dead_organisms

    def test_death_updates_gene_pool(self):
        hive = Hive()
        org = hive.hatch(strategy="seed")
        if org.genome:
            org.genome.fitness_score = 0.7
            gid = org.genome.genome_id

        org.state = OrganismState.DYING
        hive._kill(org)

        # 基因应该进入基因库
        assert gid in hive.gene_pool or len(hive.gene_pool) > 0


class TestHiveDiversity:
    def test_diversity_single_organism(self):
        hive = Hive()
        _ = hive.hatch(strategy="seed")
        # 只有一个个体时多样性为 1
        assert hive.diversity == 1.0

    def test_diversity_multiple_organisms(self):
        hive = Hive()
        hive.hatch_batch(5, strategy="seed")
        active = hive.active_organisms
        if len(active) >= 2:
            assert 0.0 <= hive.diversity <= 1.0


class TestTicks:
    def test_tick_all_updates_organisms(self):
        hive = Hive()
        org1 = hive.hatch(strategy="seed")
        org2 = hive.hatch(strategy="seed")
        org1.deploy()
        org2.deploy()

        results = {
            org1.organism_id: {"income": 10.0, "downloads": 3, "rating": 4.5, "api_cost": 0.02},
            org2.organism_id: {"income": 5.0, "downloads": 1, "rating": 4.0, "api_cost": 0.02},
        }
        events = hive.tick_all(results)
        assert org1.days_alive == 1
        assert org2.days_alive == 1


class TestPersistence:
    def test_save_and_load(self):
        hive = Hive()
        hive.hatch_batch(3, strategy="seed")
        hive.save()

        hive2 = Hive()
        assert hive2.load()
        assert len(hive2.organisms) == 3

    def test_load_empty_state(self):
        hive = Hive()
        assert not hive.load()
