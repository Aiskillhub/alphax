"""Layer 3: Alpha Brain 测试"""
import pytest
from core.genome import Genome, SEED_GENOMES, Category, PricingModel
from brain.alpha_brain import AlphaBrain
from brain.value_network import ValueNetwork, ValuePrediction
from brain.policy_network import PolicyNetwork, Candidate
from brain.mcts_engine import MctsEngine, MctsResult


# ── ValueNetwork ──

class TestValueNetwork:
    def test_heuristic_predict_no_data(self):
        vn = ValueNetwork()
        g = SEED_GENOMES[0]
        pred = vn._heuristic_predict(g, [])
        assert pred.predicted_monthly_revenue > 0
        assert 0 <= pred.predicted_survival_prob <= 1

    def test_heuristic_predict_with_data(self):
        vn = ValueNetwork()
        g = SEED_GENOMES[0]
        training = [
            {"genome_id": "g1", "days_alive": 30, "total_earned": 200, "survived": True},
            {"genome_id": "g2", "days_alive": 15, "total_earned": 80, "survived": True},
            {"genome_id": "g3", "days_alive": 5, "total_earned": 10, "survived": False},
        ]
        pred = vn._heuristic_predict(g, training)
        assert pred.predicted_monthly_revenue > 0
        assert pred.confidence > 0

    def test_evaluate_tracks_accuracy(self):
        vn = ValueNetwork()
        g = SEED_GENOMES[0]
        pred = ValuePrediction(
            genome_id=g.genome_id,
            predicted_monthly_revenue=100,
            predicted_survival_prob=0.7,
            confidence=0.5,
            reasoning="test",
        )
        ev = vn.evaluate(pred, actual_revenue=120, actual_survived=True)
        assert ev["survival_correct"]
        assert ev["revenue_error_pct"] < 0.5

    def test_evaluate_wrong_survival(self):
        vn = ValueNetwork()
        g = SEED_GENOMES[0]
        pred = ValuePrediction(
            genome_id=g.genome_id,
            predicted_monthly_revenue=50,
            predicted_survival_prob=0.3,
            confidence=0.5,
            reasoning="test",
        )
        ev = vn.evaluate(pred, actual_revenue=50, actual_survived=True)
        assert not ev["survival_correct"]


# ── PolicyNetwork ──

class TestPolicyNetwork:
    def test_generates_candidates(self):
        pn = PolicyNetwork()
        candidates = pn.generate_candidates({}, 50)
        assert len(candidates) == 20  # capped at 20
        assert all(isinstance(c, Candidate) for c in candidates)

    def test_exploit_vs_explore(self):
        pn = PolicyNetwork()
        # Create a gene pool with known good genes
        pool = {}
        for i in range(3):
            g = SEED_GENOMES[i]
            g.fitness_score = 0.8
            g.times_succeeded = 5
            g.times_used = 10
            pool[g.genome_id] = g

        candidates = pn.generate_candidates(pool, 50)
        exploit = [c for c in candidates if c.source == "exploit"]
        explore = [c for c in candidates if c.source == "explore"]
        assert len(exploit) > 0
        assert len(explore) > 0

    def test_select_for_mcts(self):
        pn = PolicyNetwork()
        candidates = pn.generate_candidates({}, 50)
        top5 = pn.select_for_mcts(candidates, n=5)
        assert len(top5) == 5
        # sorted by priority
        for i in range(len(top5) - 1):
            assert top5[i].priority >= top5[i + 1].priority or (
                top5[i].priority == top5[i + 1].priority
            )


# ── MctsEngine ──

class TestMctsEngine:
    def test_evaluate_candidates(self):
        mcts = MctsEngine()
        g1 = SEED_GENOMES[0]
        g2 = SEED_GENOMES[1].mutate()
        candidates = [
            Candidate(genome=g1, source="exploit", priority=0.8, rationale="test"),
            Candidate(genome=g2, source="explore", priority=0.3, rationale="test"),
        ]
        results = mcts.evaluate(candidates)
        assert len(results) == 2
        assert all(isinstance(r, MctsResult) for r in results)

    def test_heuristic_evaluate(self):
        mcts = MctsEngine()
        g = SEED_GENOMES[0]
        result = mcts._heuristic_evaluate(g)
        assert result.expected_monthly_revenue > 0
        assert 0 <= result.survival_probability <= 1
        assert result.confidence == 0.3

    def test_select_best(self):
        mcts = MctsEngine()
        g1 = SEED_GENOMES[0]
        g2 = SEED_GENOMES[1]
        results = [
            MctsResult(
                genome=g1, expected_monthly_revenue=50, survival_probability=0.5,
                best_scenario="neutral", worst_case_revenue=10,
                reasoning="ok", confidence=0.5,
            ),
            MctsResult(
                genome=g2, expected_monthly_revenue=100, survival_probability=0.8,
                best_scenario="optimistic", worst_case_revenue=30,
                reasoning="better", confidence=0.6,
            ),
        ]
        best = mcts.select_best(results)
        assert best is not None
        assert best.genome == g2

    def test_best_genome(self):
        mcts = MctsEngine()
        g1 = SEED_GENOMES[0]
        g2 = SEED_GENOMES[1].mutate()
        candidates = [
            Candidate(genome=g1, source="exploit", priority=0.5, rationale="t"),
            Candidate(genome=g2, source="exploit", priority=0.5, rationale="t"),
        ]
        mcts.evaluate(candidates)
        best = mcts.best_genome()
        assert best is not None
        assert isinstance(best, Genome)


# ── AlphaBrain ──

class TestAlphaBrain:
    def test_decide_returns_valid_genome(self):
        ab = AlphaBrain()
        g = SEED_GENOMES[0]
        pool = {g.genome_id: g}
        decision = ab.decide(gene_pool=pool, fund_balance=100, training_data=[])
        assert decision.genome is not None
        assert isinstance(decision.genome, Genome)
        assert decision.source in ("mcts", "exploit", "explore", "inherit")

    def test_decide_with_empty_pool(self):
        ab = AlphaBrain()
        decision = ab.decide(gene_pool={}, fund_balance=100, training_data=[])
        assert decision.genome is not None
        # with API key set, goes through full pipeline (mcts)
        # without, falls back to explore or inherit
        assert decision.source in ("mcts", "explore", "inherit")

    def test_decide_with_training_data(self):
        ab = AlphaBrain()
        g = SEED_GENOMES[0]
        pool = {g.genome_id: g}
        training = [
            {"genome_id": "g1", "days_alive": 30, "total_earned": 200, "survived": True},
        ] * 10
        decision = ab.decide(gene_pool=pool, fund_balance=100, training_data=training)
        assert decision.genome is not None

    def test_force_explore(self):
        ab = AlphaBrain()
        g = SEED_GENOMES[0]
        pool = {g.genome_id: g}
        decision = ab.decide(
            gene_pool=pool, fund_balance=100, training_data=[], force_explore=True,
        )
        assert decision.genome is not None

    def test_summary(self):
        ab = AlphaBrain()
        # make a few decisions
        g = SEED_GENOMES[0]
        pool = {g.genome_id: g}
        for _ in range(3):
            ab.decide(gene_pool=pool, fund_balance=100, training_data=[])

        stats = ab.summary
        assert stats["total_decisions"] == 3
        assert "mcts_decisions" in stats
        assert "explore_decisions" in stats
        assert "inherit_decisions" in stats
        assert "hit_rate" in stats
