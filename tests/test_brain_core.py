"""brain/core 未测模块测试"""
import pytest
import json
from pathlib import Path

from brain.knowledge import KnowledgeEngine
from brain.memory import MemorySystem
from core.api_utils import extract_json


# ── KnowledgeEngine ──

def _clean_knowledge(tmp_path):
    """创建隔离的 KnowledgeEngine"""
    ke = KnowledgeEngine()
    ke._path = tmp_path / "knowledge.json"
    ke.market_insights = {}
    ke.strategy_map = []
    ke.meta_patterns = []
    return ke


class TestKnowledgeEngine:
    def test_best_strategy_no_data(self, tmp_path):
        ke = _clean_knowledge(tmp_path)
        result = ke.best_strategy_for("ai_chat", "low")
        assert result is None

    def test_best_strategy_finds_match(self, tmp_path):
        ke = _clean_knowledge(tmp_path)
        ke.learn_from_result("ai_chat", 3.99, "one_time", "english", "low",
                             {"survived": True, "net_profit": 50, "survival_rate": 0.8})
        ke.learn_from_result("ai_chat", 9.99, "subscription", "english", "low",
                             {"survived": True, "net_profit": 120, "survival_rate": 0.7})
        result = ke.best_strategy_for("ai_chat", "low")
        assert result is not None
        assert result["price_point"] == 9.99
        assert result["expected_revenue"] == 120

    def test_category_health_unknown(self, tmp_path):
        ke = _clean_knowledge(tmp_path)
        health = ke.category_health("nonexistent")
        assert health["status"] == "unknown"
        assert health["samples"] == 0

    def test_category_health_hot(self, tmp_path):
        ke = _clean_knowledge(tmp_path)
        ke.learn_from_result("ai_chat", 3.99, "one_time", "english", "low",
                             {"survived": True, "net_profit": 50})
        ke.learn_from_result("ai_chat", 4.99, "one_time", "english", "low",
                             {"survived": True, "net_profit": 60})
        health = ke.category_health("ai_chat")
        assert health["status"] == "hot"
        assert health["samples"] == 2
        assert health["survival_rate"] == 1.0

    def test_category_health_cold(self, tmp_path):
        ke = _clean_knowledge(tmp_path)
        ke.learn_from_result("ai_chat", 9.99, "subscription", "english", "low",
                             {"survived": False, "net_profit": -10})
        ke.learn_from_result("ai_chat", 9.99, "subscription", "english", "low",
                             {"survived": False, "net_profit": -5})
        health = ke.category_health("ai_chat")
        assert health["status"] == "cold"
        assert health["survival_rate"] == 0.0

    def test_learn_updates_market_insights(self, tmp_path):
        ke = _clean_knowledge(tmp_path)
        ke.learn_from_result("ai_chat", 3.99, "one_time", "english", "low",
                             {"survived": True, "net_profit": 50})
        assert "ai_chat" in ke.market_insights
        assert ke.market_insights["ai_chat"]["total"] == 1
        assert ke.market_insights["ai_chat"]["survived"] == 1

    def test_save_and_load(self, tmp_path):
        # Write with one engine
        ke = KnowledgeEngine()
        ke._path = tmp_path / "knowledge.json"
        ke.market_insights = {}
        ke.strategy_map = []
        ke.meta_patterns = []
        ke.learn_from_result("ai_chat", 3.99, "one_time", "english", "low",
                             {"survived": True, "net_profit": 50})

        # Load with a second engine (don't reset state, let __post_init__ load)
        ke2 = KnowledgeEngine()
        ke2._path = tmp_path / "knowledge.json"
        # Re-trigger load
        if ke2._path.exists():
            import json
            data = json.loads(ke2._path.read_text())
            ke2.market_insights = data.get("market_insights", {})
            ke2.strategy_map = data.get("strategy_map", [])
            ke2.meta_patterns = data.get("meta_patterns", [])

        assert len(ke2.strategy_map) == 1
        assert "ai_chat" in ke2.market_insights

    def test_meta_patterns_below_threshold(self, tmp_path):
        ke = _clean_knowledge(tmp_path)
        for i in range(5):
            ke.learn_from_result("ai_chat", 3.99, "one_time", "english", "low",
                                 {"survived": True, "net_profit": 50})
        assert len(ke.meta_patterns) == 0


# ── MemorySystem ──

class TestMemorySystem:
    def test_record_deploy(self, tmp_path):
        from config import config
        orig = config.ledger_path
        config.ledger_path = tmp_path / "ledger.jsonl"
        try:
            ms = MemorySystem()
            ms.ledger = []  # reset
            ms.record_deploy("org_1", "gen_1", "Test Product")
            assert len(ms.ledger) == 1
            assert ms.ledger[0]["type"] == "deploy"
            assert ms.ledger[0]["product_name"] == "Test Product"
        finally:
            config.ledger_path = orig

    def test_record_result(self, tmp_path):
        from config import config
        orig = config.ledger_path
        config.ledger_path = tmp_path / "ledger.jsonl"
        try:
            ms = MemorySystem()
            ms.ledger = []
            ms.record_result("org_1", "gen_1", days_alive=30,
                             total_earned=100, total_burned=20,
                             survived=True, avg_rating=4.5)
            assert len(ms.ledger) == 1
            entry = ms.ledger[0]
            assert entry["type"] == "result"
            assert entry["survived"] is True
            assert entry["net_profit"] == 80
        finally:
            config.ledger_path = orig

    def test_record_insight(self, tmp_path):
        from config import config
        orig = config.ledger_path
        config.ledger_path = tmp_path / "ledger.jsonl"
        try:
            ms = MemorySystem()
            ms.ledger = []
            ms.record_insight("market", "低价策略有效", confidence=0.8)
            assert len(ms.ledger) == 1
            assert ms.ledger[0]["category"] == "market"
        finally:
            config.ledger_path = orig

    def test_get_training_data_below_min(self, tmp_path):
        ms = MemorySystem()
        ms.ledger = []
        data = ms.get_training_data(min_samples=10)
        assert data == []

    def test_get_training_data_enough(self, tmp_path):
        ms = MemorySystem()
        ms.ledger = [{"type": "result", "genome_id": f"g{i}", "survived": True}
                     for i in range(10)]
        data = ms.get_training_data(min_samples=10)
        assert len(data) == 10

    def test_get_successful_and_failed(self, tmp_path):
        ms = MemorySystem()
        ms.ledger = [
            {"type": "result", "genome_id": "g1", "survived": True},
            {"type": "result", "genome_id": "g2", "survived": False},
            {"type": "result", "genome_id": "g3", "survived": True},
            {"type": "deploy", "organism_id": "x", "genome_id": "x", "product_name": "x"},
        ]
        assert ms.get_successful_genomes() == ["g1", "g3"]
        assert ms.get_failed_genomes() == ["g2"]

    def test_get_insights(self, tmp_path):
        ms = MemorySystem()
        ms.ledger = [
            {"type": "insight", "category": "market", "content": "A"},
            {"type": "insight", "category": "pricing", "content": "B"},
            {"type": "result", "genome_id": "g1", "survived": True},
        ]
        all_insights = ms.get_insights()
        assert len(all_insights) == 2
        market_only = ms.get_insights(category="market")
        assert len(market_only) == 1

    def test_query_knowledge_graph_no_superbrain(self, tmp_path):
        ms = MemorySystem()
        result = ms.query_knowledge_graph("test")
        assert result == []

    def test_get_knowledge_stats_no_superbrain(self, tmp_path):
        ms = MemorySystem()
        stats = ms.get_knowledge_stats()
        assert stats["available"] is False

    def test_remember_genome_and_pattern(self, tmp_path):
        """验证这些方法不抛异常"""
        ms = MemorySystem()
        ms.ledger = []
        ms.remember_genome("g1", 0.8, 0.7, "Test")
        ms.remember_market_pattern("low_price_wins", "detail", 0.6)
        # Should not raise


# ── api_utils ──

class TestApiUtils:
    def test_extract_json_plain(self):
        assert extract_json('{"hello": "world"}') == '{"hello": "world"}'

    def test_extract_json_with_json_tag(self):
        text = 'some text ```json\n{"key": "val"}\n``` more text'
        assert extract_json(text) == '{"key": "val"}'

    def test_extract_json_with_code_fence(self):
        text = 'prefix ```\n{"a": 1}\n``` suffix'
        assert extract_json(text) == '{"a": 1}'

    def test_extract_json_no_code_fence(self):
        text = 'plain text without fences'
        assert extract_json(text) == 'plain text without fences'
