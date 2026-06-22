"""Layer 4: Agent Economy 测试"""
import pytest
from pathlib import Path

from layer4.service_directory import ServiceDirectory, Capability
from layer4.bidding_engine import BiddingEngine
from layer4.escrow import Escrow
from layer4.reputation import ReputationSystem


def _mkcap(name: str) -> Capability:
    return Capability(name=name, description=f"Can {name}",
                      input_schema={}, output_schema={})


# ── ServiceDirectory ──

class TestServiceDirectory:
    def test_register_agent(self, tmp_path):
        sd = ServiceDirectory(_path=tmp_path / "sd.json")
        caps = [_mkcap("code_gen"), _mkcap("listing_copy")]
        p = sd.register("org_1", "Chat Export Pro", capabilities=caps)
        assert p.agent_id == "org_1"
        assert len(sd.profiles) == 1

    def test_find_by_capability(self, tmp_path):
        sd = ServiceDirectory(_path=tmp_path / "sd.json")
        sd.register("a1", "Coder", [_mkcap("code_gen")])
        sd.register("a2", "Writer", [_mkcap("listing_copy")])
        sd.register("a3", "Fullstack", [_mkcap("code_gen"), _mkcap("testing")])
        coders = sd.find_by_capability("code_gen")
        assert len(coders) >= 1

    def test_find_no_match(self, tmp_path):
        sd = ServiceDirectory(_path=tmp_path / "sd.json")
        sd.register("a1", "Coder", [_mkcap("code_gen")])
        results = sd.find_by_capability("nonexistent")
        assert len(results) == 0

    def test_unregister(self, tmp_path):
        sd = ServiceDirectory(_path=tmp_path / "sd.json")
        sd.register("a1", "Test", [_mkcap("code_gen")])
        sd.unregister("a1")
        assert "a1" not in sd.profiles

    def test_add_capability(self, tmp_path):
        sd = ServiceDirectory(_path=tmp_path / "sd.json")
        sd.register("a1", "Coder", [_mkcap("code_gen")])
        sd.add_capability("a1", _mkcap("testing"))
        assert len(sd.profiles["a1"].capabilities) == 2


# ── BiddingEngine ──

class TestBiddingEngine:
    def test_post_demand(self, tmp_path):
        be = BiddingEngine(_path=tmp_path / "bidding.json")
        demand = be.post_demand(
            requester_id="org_1",
            capability="code_gen",
            description="Need content script",
            max_budget=5.0,
        )
        assert demand.requester_id == "org_1"
        assert demand.capability_needed == "code_gen"

    def test_place_bid(self, tmp_path):
        be = BiddingEngine(_path=tmp_path / "bidding.json")
        d = be.post_demand("org_1", "code_gen", "test", 5.0)
        bid = be.place_bid(d.demand_id, "org_2", 3.5,
                           estimated_quality=0.8, estimated_hours=2)
        assert bid is not None
        assert bid.price == 3.5

    def test_place_bid_over_budget(self, tmp_path):
        be = BiddingEngine(_path=tmp_path / "bidding.json")
        d = be.post_demand("org_1", "code_gen", "test", 5.0)
        bid = be.place_bid(d.demand_id, "org_2", 10.0)
        assert bid is None

    def test_place_bid_nonexistent_demand(self, tmp_path):
        be = BiddingEngine(_path=tmp_path / "bidding.json")
        bid = be.place_bid("nonexistent", "org_2", 3.0)
        assert bid is None

    def test_deals_storage(self, tmp_path):
        be = BiddingEngine(_path=tmp_path / "bidding.json")
        assert len(be.deals) == 0
        be.deals
        assert True  # just checking deals exists


# ── Escrow ──

class TestEscrow:
    def test_fund(self, tmp_path):
        escrow = Escrow(_path=tmp_path / "escrow.json")
        tx = escrow.fund(deal_id="d1", buyer_id="buyer", seller_id="seller", amount=5.0)
        assert tx is not None
        assert tx.amount == 5.0
        assert len(escrow.transactions) == 1

    def test_fund_zero_amount(self, tmp_path):
        escrow = Escrow(_path=tmp_path / "escrow.json")
        tx = escrow.fund("d1", "b", "s", 0)
        assert tx is None

    def test_deliver_then_accept(self, tmp_path):
        escrow = Escrow(_path=tmp_path / "escrow.json")
        tx = escrow.fund("d1", "buyer", "seller", 10.0)
        assert escrow.deliver(tx.tx_id)
        assert escrow.accept(tx.tx_id)

    def test_cannot_accept_before_deliver(self, tmp_path):
        escrow = Escrow(_path=tmp_path / "escrow.json")
        tx = escrow.fund("d1", "buyer", "seller", 10.0)
        assert not escrow.accept(tx.tx_id)  # must deliver first

    def test_dispute_and_resolve_refund(self, tmp_path):
        escrow = Escrow(_path=tmp_path / "escrow.json")
        tx = escrow.fund("d1", "buyer", "seller", 10.0)
        escrow.deliver(tx.tx_id)
        assert escrow.dispute(tx.tx_id)
        assert escrow.resolve_dispute(tx.tx_id, refund=True)

    def test_dispute_and_resolve_release(self, tmp_path):
        escrow = Escrow(_path=tmp_path / "escrow.json")
        tx = escrow.fund("d1", "buyer", "seller", 10.0)
        escrow.deliver(tx.tx_id)
        escrow.dispute(tx.tx_id)
        assert escrow.resolve_dispute(tx.tx_id, refund=False)

    def test_pending_count(self, tmp_path):
        escrow = Escrow(_path=tmp_path / "escrow.json")
        escrow.fund("d1", "b", "s", 5.0)
        assert escrow.pending_count() == 1


# ── ReputationSystem ──

class TestReputationSystem:
    def test_get_or_create_new(self, tmp_path):
        rs = ReputationSystem(_path=tmp_path / "rep.json")
        rep = rs.get_or_create("new_agent")
        assert rep.agent_id == "new_agent"
        assert rep.overall == 3.0  # default for new agents

    def test_rate_updates_score(self, tmp_path):
        rs = ReputationSystem(_path=tmp_path / "rep.json")
        rs.rate("from", "to", "d1", score=5.0, comment="great")
        rep = rs.get_or_create("to")
        assert rep.total_ratings == 1
        assert rep.avg_rating == 5.0

    def test_record_deal_complete(self, tmp_path):
        rs = ReputationSystem(_path=tmp_path / "rep.json")
        rs.record_deal_complete("agent_1", success=True)
        rs.record_deal_complete("agent_1", success=True)
        rs.record_deal_complete("agent_1", success=False)
        rep = rs.get_or_create("agent_1")
        assert rep.total_deals == 3
        assert rep.completed_deals == 2
        assert rep.completion_rate == pytest.approx(2 / 3)

    def test_stake(self, tmp_path):
        rs = ReputationSystem(_path=tmp_path / "rep.json")
        rs.stake("agent_1", 50.0)
        rep = rs.get_or_create("agent_1")
        assert rep.staked_amount == 50.0

    def test_rank(self, tmp_path):
        rs = ReputationSystem(_path=tmp_path / "rep.json")
        # build reputation for a1
        rs.stake("a1", 50)
        for _ in range(10):
            rs.record_deal_complete("a1", success=True)
        rs.rate("x", "a1", "d1", 5.0)

        # a2 is bad
        for _ in range(5):
            rs.record_deal_complete("a2", success=False)

        ranked = rs.rank(5)
        assert len(ranked) >= 1

    def test_is_trusted(self, tmp_path):
        rs = ReputationSystem(_path=tmp_path / "rep.json")
        rs.stake("good", 50)
        for _ in range(10):
            rs.record_deal_complete("good", success=True)
        rs.rate("x", "good", "d1", 5.0)
        assert rs.is_trusted("good")

    def test_untrustworthy(self, tmp_path):
        rs = ReputationSystem(_path=tmp_path / "rep.json")
        for _ in range(5):
            rs.record_deal_complete("bad", success=False)
        rs.rate("x", "bad", "d1", 1.0)
        assert "bad" in rs.untrustworthy()

    def test_stats(self, tmp_path):
        rs = ReputationSystem(_path=tmp_path / "rep.json")
        rs.get_or_create("a1")
        rs.rate("x", "a1", "d1", 4.0)
        stats = rs.stats()
        assert stats["total_agents"] >= 1
