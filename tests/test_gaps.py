"""补充已测模块的遗漏方法测试"""
import pytest
from pathlib import Path

from layer1.semantic_git import SemanticGit, ChangeType
from layer1.intent_code import IntentCode, Constraint, ConstraintType
from layer1.autonomous_ci import AutonomousCI
from layer4.service_directory import ServiceDirectory, Capability
from layer4.bidding_engine import BiddingEngine
from layer4.escrow import Escrow
from brain.alpha_brain import AlphaBrain
from core.genome import SEED_GENOMES


def _mkcap(name: str) -> Capability:
    return Capability(name=name, description=f"Can {name}",
                      input_schema={}, output_schema={})


# ── SemanticGit 遗漏 ──

class TestSemanticGitGaps:
    def test_get_genome_performance(self, tmp_path):
        git = SemanticGit(_path=tmp_path / "git.json")
        git.commit("feature A", ChangeType.FEATURE, ["a.js"], "a1", "o1", "g1")
        git.commit("fix A", ChangeType.FIX, ["a.js"], "a1", "o1", "g1")
        git.commit("feature B", ChangeType.FEATURE, ["b.js"], "a2", "o2", "g2")
        perf = git.get_genome_performance("g1")
        assert perf["commits"] == 2
        assert perf["features"] == 1
        assert perf["bugs_fixed"] == 1

    def test_get_genome_performance_empty(self, tmp_path):
        git = SemanticGit(_path=tmp_path / "git.json")
        perf = git.get_genome_performance("nonexistent")
        assert perf["commits"] == 0

    def test_summary(self, tmp_path):
        git = SemanticGit(_path=tmp_path / "git.json")
        git.commit("A", ChangeType.FEATURE, ["a.js"], "a1", "o1", "g1")
        git.commit("B", ChangeType.FIX, ["b.js"], "a2", "o2", "g2")
        s = git.summary()
        assert s["total_commits"] == 2
        assert s["unique_organisms"] == 2
        assert s["unique_genomes"] == 2


# ── IntentCode 遗漏 ──

class TestIntentCodeGaps:
    def test_validate_constraints(self, tmp_path):
        ic = IntentCode(_path=tmp_path / "ic.json")
        block = ic.store("test", {"a.js": "x" * 100}, organism_id="o1", genome_id="g1")
        result = ic.validate_constraints(block.block_id)
        assert result["valid"] is True

    def test_validate_constraints_size_fail(self, tmp_path):
        ic = IntentCode(_path=tmp_path / "ic.json")
        block = ic.store(
            "test",
            {"a.js": "x" * 5000},
            constraints=[Constraint(ConstraintType.SIZE, "size < 100", 100, "bytes")],
            organism_id="o1",
            genome_id="g1",
        )
        result = ic.validate_constraints(block.block_id)
        assert result["valid"] is False

    def test_validate_constraints_not_found(self, tmp_path):
        ic = IntentCode(_path=tmp_path / "ic.json")
        result = ic.validate_constraints("nonexistent")
        assert result["valid"] is False

    def test_diff_blocks(self, tmp_path):
        ic = IntentCode(_path=tmp_path / "ic.json")
        a = ic.store("same intent", {"a.js": "code"}, organism_id="o1", genome_id="g1")
        b = ic.store("same intent", {"b.js": "code"}, organism_id="o1", genome_id="g1")
        diff = ic.diff_blocks(a.block_id, b.block_id)
        assert diff["same_intent"] is True
        assert "b.js" in diff["files_added"]

    def test_diff_blocks_not_found(self, tmp_path):
        ic = IntentCode(_path=tmp_path / "ic.json")
        diff = ic.diff_blocks("x", "y")
        assert "error" in diff

    def test_summary(self, tmp_path):
        ic = IntentCode(_path=tmp_path / "ic.json")
        ic.store("A", {"a.js": "line1\nline2"}, organism_id="o1", genome_id="g1")
        ic.store("B", {"b.js": "line"}, organism_id="o2", genome_id="g2")
        s = ic.summary()
        assert s["total_blocks"] == 2
        assert s["total_lines"] == 3


# ── AutonomousCI 遗漏 ──

class TestAutonomousCIGaps:
    def test_stats(self, tmp_path):
        ci = AutonomousCI(_path=tmp_path / "ci.json")
        ci.run("c1", "o1", {"a.js": "ok"}, "test")
        ci.run("c2", "o2", {"b.js": "ok"}, "test")
        s = ci.stats()
        assert s["total_runs"] == 2

    def test_stats_empty(self, tmp_path):
        ci = AutonomousCI(_path=tmp_path / "ci.json")
        s = ci.stats()
        assert s["total_runs"] == 0


# ── ServiceDirectory 遗漏 ──

class TestServiceDirectoryGaps:
    def test_find_by_keyword(self, tmp_path):
        sd = ServiceDirectory(_path=tmp_path / "sd.json")
        caps = [_mkcap("chat_export")]
        sd.register("a1", "Chat Export Pro", caps)
        sd.register("a2", "Code Helper", [_mkcap("code_gen")])
        results = sd.find_by_keyword("chat")
        assert len(results) >= 1

    def test_find_by_keyword_no_match(self, tmp_path):
        sd = ServiceDirectory(_path=tmp_path / "sd.json")
        sd.register("a1", "Coder", [_mkcap("code_gen")])
        results = sd.find_by_keyword("zzz_nonexistent")
        assert len(results) == 0

    def test_top_performers(self, tmp_path):
        sd = ServiceDirectory(_path=tmp_path / "sd.json")
        sd.register("a1", "Coder")
        sd.register("a2", "Writer")
        sd.profiles["a1"].total_earned = 100
        sd.profiles["a2"].total_earned = 50
        top = sd.top_performers(2)
        assert top[0].agent_id == "a1"

    def test_summary(self, tmp_path):
        sd = ServiceDirectory(_path=tmp_path / "sd.json")
        sd.register("a1", "Coder", [_mkcap("code_gen"), _mkcap("test")])
        sd.register("a2", "Writer", [_mkcap("listing_copy")])
        s = sd.summary()
        assert s["total_agents"] == 2
        assert s["active_agents"] == 2
        assert s["total_capabilities"] == 3
        assert s["unique_capabilities"] == 3


# ── BiddingEngine 遗漏 ──

class TestBiddingEngineGaps:
    def test_select_winner(self, tmp_path):
        be = BiddingEngine(_path=tmp_path / "bidding.json")
        d = be.post_demand("org_1", "code_gen", "test", 10.0)
        be.place_bid(d.demand_id, "org_2", 3.0, estimated_quality=0.9, estimated_hours=2)
        be.place_bid(d.demand_id, "org_3", 5.0, estimated_quality=0.5, estimated_hours=4)
        winner = be.select_winner(d.demand_id)
        assert winner is not None
        # Higher quality/lower price/lower hours should win
        assert winner.bidder_id == "org_2"

    def test_select_winner_no_bids(self, tmp_path):
        be = BiddingEngine(_path=tmp_path / "bidding.json")
        d = be.post_demand("org_1", "code_gen", "test", 10.0)
        winner = be.select_winner(d.demand_id)
        assert winner is None

    def test_active_demands(self, tmp_path):
        be = BiddingEngine(_path=tmp_path / "bidding.json")
        be.post_demand("org_1", "code_gen", "test", 10.0)
        be.post_demand("org_2", "listing_copy", "test", 5.0)
        active = be.active_demands()
        assert len(active) == 2

    def test_stats(self, tmp_path):
        be = BiddingEngine(_path=tmp_path / "bidding.json")
        d = be.post_demand("org_1", "code_gen", "test", 10.0)
        be.place_bid(d.demand_id, "org_2", 5.0)
        be.place_bid(d.demand_id, "org_3", 3.0)
        be.select_winner(d.demand_id)
        s = be.stats()
        assert s["total_demands"] == 1
        assert s["filled"] == 1
        assert s["total_bids"] == 2
        assert s["total_deals"] == 1


# ── Escrow 遗漏 ──

class TestEscrowGaps:
    def test_disputed_count(self, tmp_path):
        escrow = Escrow(_path=tmp_path / "escrow.json")
        tx = escrow.fund("d1", "buyer", "seller", 10.0)
        escrow.deliver(tx.tx_id)
        escrow.dispute(tx.tx_id)
        assert escrow.disputed_count() == 1

    def test_disputed_count_zero(self, tmp_path):
        escrow = Escrow(_path=tmp_path / "escrow.json")
        assert escrow.disputed_count() == 0

    def test_stats(self, tmp_path):
        escrow = Escrow(_path=tmp_path / "escrow.json")
        tx = escrow.fund("d1", "buyer", "seller", 10.0)
        escrow.deliver(tx.tx_id)
        escrow.accept(tx.tx_id)
        s = escrow.stats()
        assert s["total_transactions"] == 1
        assert s["accepted"] == 1
        assert s["total_volume"] == 10.0


# ── AlphaBrain 遗漏 ──

class TestAlphaBrainGaps:
    def test_learn_from_outcome(self):
        ab = AlphaBrain()
        g = SEED_GENOMES[0]
        pool = {g.genome_id: g}
        decision = ab.decide(gene_pool=pool, fund_balance=100, training_data=[])
        ab.learn_from_outcome(decision, actual_revenue=120, actual_survived=True)
        assert len(ab.value.accuracy_log) >= 1

    def test_learn_from_outcome_failure(self):
        ab = AlphaBrain()
        g = SEED_GENOMES[0]
        pool = {g.genome_id: g}
        decision = ab.decide(gene_pool=pool, fund_balance=100, training_data=[])
        ab.learn_from_outcome(decision, actual_revenue=10, actual_survived=False)
        assert len(ab.value.accuracy_log) >= 1

    def test_hit_rate_default(self):
        ab = AlphaBrain()
        assert ab.hit_rate == 0.5

    def test_hit_rate_after_learning(self):
        ab = AlphaBrain()
        g = SEED_GENOMES[0]
        pool = {g.genome_id: g}
        d = ab.decide(gene_pool=pool, fund_balance=100, training_data=[])
        ab.learn_from_outcome(d, actual_revenue=100, actual_survived=True)
        assert ab.hit_rate == 1.0
