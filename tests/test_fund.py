"""资金池测试：收入分配、孵化支出、持久化"""

import pytest
from capital.fund import Fund, Transaction


class TestFundInitialization:
    def test_new_fund_starts_empty(self):
        fund = Fund()
        assert fund.pool_balance == 0.0
        assert fund.total_platform_fees == 0.0

    def test_inject_initial(self):
        fund = Fund()
        fund.inject_initial(100.0)
        assert fund.pool_balance == 100.0
        assert len(fund.transactions) == 1


class TestIncomeDistribution:
    def test_distribute_splits_correctly(self):
        fund = Fund()
        result = fund.distribute_income(100.0, "org_1")

        # 10% 平台费 = $10
        assert result["platform_fee"] == pytest.approx(10.0)
        # 剩余 $90: 70% 个体 = $63, 30% 池 = $27
        assert result["organism_share"] == pytest.approx(63.0)
        assert result["pool_contribution"] == pytest.approx(27.0)

        assert fund.pool_balance == pytest.approx(27.0)
        assert fund.total_platform_fees == pytest.approx(10.0)

    def test_distribute_zero_income(self):
        fund = Fund()
        result = fund.distribute_income(0.0, "org_x")
        assert result["platform_fee"] == 0.0
        assert result["organism_share"] == 0.0
        assert fund.pool_balance == 0.0

    def test_multiple_distributions_accumulate(self):
        fund = Fund()
        fund.distribute_income(50.0, "a")
        fund.distribute_income(50.0, "b")
        # 每次上缴 $13.5 到池
        assert fund.pool_balance == pytest.approx(27.0)


class TestHatchSpending:
    def test_spend_hatch_deducts(self):
        fund = Fund()
        fund.inject_initial(50.0)
        assert fund.pool_balance == 50.0

        success = fund.spend_hatch("org_1")
        assert success
        assert fund.pool_balance == 45.0  # hatch_energy = 5.0
        assert fund.total_hatch_costs == 5.0

    def test_spend_hatch_fails_when_empty(self):
        fund = Fund()
        assert not fund.can_hatch
        assert not fund.spend_hatch("org_1")

    def test_can_hatch_flag(self):
        fund = Fund()
        assert not fund.can_hatch
        fund.inject_initial(50.0)
        assert fund.can_hatch


class TestSummary:
    def test_summary_reflects_state(self):
        fund = Fund()
        fund.inject_initial(100)
        fund.distribute_income(50, "a")
        s = fund.summary
        assert s["pool_balance"] > 0
        assert s["transaction_count"] == 2


class TestPersistence:
    def test_save_and_load(self, tmp_path):
        fund = Fund()
        fund._path = tmp_path / "fund.json"
        fund.inject_initial(100)
        fund.distribute_income(50, "org_1")

        fund2 = Fund()
        fund2._path = tmp_path / "fund.json"
        fund2.load()

        assert fund2.pool_balance == fund.pool_balance
        assert len(fund2.transactions) == len(fund.transactions)
