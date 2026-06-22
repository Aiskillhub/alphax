"""个体生命周期测试：状态机、能量系统、生死判定"""

import pytest
from core.organism import Organism, OrganismState, DailyRecord
from core.genome import Genome, Category


class TestOrganismLifecycle:
    def test_new_organism_is_hatching(self):
        org = Organism()
        assert org.state == OrganismState.HATCHING
        assert org.energy == 0.0
        assert org.days_alive == 0

    def test_hatch_sets_genome_and_energy(self):
        org = Organism()
        genome = Genome(category=Category.AI_CHAT)
        org.hatch(genome, initial_energy=5.0)
        assert org.genome is not None
        assert org.energy == 5.0
        assert org.state == OrganismState.HATCHING
        assert org.hatched_at != ""

    def test_hatch_default_energy(self):
        org = Organism()
        org.hatch(Genome())
        assert org.energy == 5.0  # config.hatch_energy

    def test_deploy_transitions_to_active(self):
        org = Organism()
        org.hatch(Genome())
        org.deploy()
        assert org.state == OrganismState.ACTIVE
        assert org.deployed_at != ""

    def test_is_alive(self):
        org = Organism()
        org.hatch(Genome())
        org.deploy()
        assert org.is_alive


class TestEnergySystem:
    def test_daily_tick_positive_income(self):
        org = Organism()
        org.hatch(Genome())
        org.deploy()
        record = org.daily_tick(income=10.0, downloads=5, rating=4.5)
        assert record.energy_delta > 0
        assert org.energy > 5.0
        assert org.days_alive == 1
        assert org.days_energy_positive == 1
        assert org.consecutive_loss_days == 0
        assert org.total_downloads == 5
        assert org.current_rating == 4.5

    def test_daily_tick_negative_income(self):
        org = Organism()
        org.hatch(Genome())
        org.deploy()
        record = org.daily_tick(income=0.0, downloads=0)
        assert record.energy_delta < 0
        assert org.days_alive == 1
        assert org.days_energy_positive == 0
        assert org.consecutive_loss_days == 1

    def test_consecutive_loss_tracking(self):
        org = Organism()
        org.hatch(Genome())
        org.deploy()
        for _ in range(3):
            org.daily_tick(income=0.0, downloads=0)
        assert org.consecutive_loss_days == 3

    def test_loss_counter_resets_on_profit(self):
        org = Organism()
        org.hatch(Genome())
        org.deploy()
        org.daily_tick(income=0.0, downloads=0)
        org.daily_tick(income=0.0, downloads=0)
        org.daily_tick(income=20.0, downloads=2)
        assert org.consecutive_loss_days == 0


class TestDeathConditions:
    def test_should_die_on_negative_energy(self):
        org = Organism()
        org.hatch(Genome())
        org.energy = -1.0
        assert org.should_die

    def test_should_die_after_consecutive_losses(self):
        org = Organism()
        org.hatch(Genome())
        org.deploy()
        for _ in range(7):
            org.daily_tick(income=0.0, downloads=0)
        assert org.consecutive_loss_days >= 7
        assert org.should_die

    def test_daily_tick_triggers_dying(self):
        org = Organism()
        org.hatch(Genome())
        org.deploy()
        for _ in range(7):
            org.daily_tick(income=0.0, downloads=0)
        assert org.state == OrganismState.DYING

    def test_die_records_state(self):
        org = Organism()
        org.hatch(Genome())
        org.deploy()
        org.die()
        assert org.state == OrganismState.DEAD
        assert org.died_at != ""


class TestBreedConditions:
    def test_cannot_breed_when_new(self):
        org = Organism()
        org.hatch(Genome())
        org.deploy()
        assert not org.can_breed

    def test_can_breed_after_min_days(self):
        org = Organism()
        org.hatch(Genome())
        org.deploy()
        # 模拟满足繁殖条件的天数
        for _ in range(30):
            org.daily_tick(income=10.0, downloads=2)
        assert org.days_alive >= 30
        assert org.days_energy_positive >= 21
        assert org.can_breed


class TestDailyHistory:
    def test_history_accumulates(self):
        org = Organism()
        org.hatch(Genome())
        org.deploy()
        for i in range(5):
            org.daily_tick(income=5.0, downloads=1)
        assert len(org.daily_history) == 5

    def test_daily_net_energy(self):
        org = Organism()
        org.hatch(Genome())
        org.deploy()
        for _ in range(7):
            org.daily_tick(income=10.0, downloads=1)
        # 7 天日均净能量 > 0
        assert org.daily_net_energy > 0


class TestSerialization:
    def test_to_dict_and_back(self):
        org = Organism()
        genome = Genome(category=Category.AI_CHAT, price_point=3.99)
        org.hatch(genome)
        org.deploy()
        org.daily_tick(income=5.0, downloads=1)

        d = org.to_dict()
        restored = Organism.from_dict(d)

        assert restored.organism_id == org.organism_id
        assert restored.energy == org.energy
        assert restored.days_alive == org.days_alive
        assert restored.state == org.state
        assert restored.genome is not None
        assert restored.genome.price_point == 3.99
