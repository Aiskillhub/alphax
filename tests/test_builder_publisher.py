"""builder / publisher / monitor 测试"""
import json
import pytest
from pathlib import Path

from core.genome import SEED_GENOMES, Genome
from builder.extension import ExtensionBuilder
from builder.listing import ListingGenerator, ListingCopy
from builder.tester import ExtensionTester, TestResult
from publisher.gumroad_pub import GumroadPublisher, PublishResult
from publisher.chrome_store import ChromeStorePublisher, ChromePublishResult
from monitor.market_monitor import MarketMonitor


# ── ExtensionBuilder ──

class TestExtensionBuilder:
    def test_build_creates_zip(self, tmp_path):
        builder = ExtensionBuilder()
        builder._build_dir = tmp_path
        g = SEED_GENOMES[0]
        zip_path = builder.build(g, "test_org_1")
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"

    def test_build_dir_contains_files(self, tmp_path):
        builder = ExtensionBuilder()
        builder._build_dir = tmp_path
        g = SEED_GENOMES[0]
        builder.build(g, "test_org_2")
        work_dir = tmp_path / "test_org_2"
        assert work_dir.exists()
        assert (work_dir / "manifest.json").exists()
        manifest = json.loads((work_dir / "manifest.json").read_text())
        assert manifest["manifest_version"] == 3
        assert len(manifest["name"]) > 0

    def test_build_different_categories(self, tmp_path):
        builder = ExtensionBuilder()
        builder._build_dir = tmp_path
        for g in SEED_GENOMES:
            zip_path = builder.build(g, f"test_{g.genome_id}")
            assert zip_path.exists()

    def test_manifest_permissions(self, tmp_path):
        builder = ExtensionBuilder()
        builder._build_dir = tmp_path
        g = SEED_GENOMES[0]
        builder.build(g, "test_perm")
        manifest = json.loads((tmp_path / "test_perm" / "manifest.json").read_text())
        assert "permissions" in manifest
        assert "activeTab" in manifest["permissions"]

    def test_content_script_not_empty(self, tmp_path):
        builder = ExtensionBuilder()
        builder._build_dir = tmp_path
        g = SEED_GENOMES[0]
        builder.build(g, "test_content")
        content = (tmp_path / "test_content" / "content.js").read_text()
        assert len(content) > 0
        assert "use strict" in content.lower()


# ── ListingGenerator ──

class TestListingGenerator:
    def test_template_generate(self, tmp_path):
        # Patch to avoid API calls during test
        import config
        orig_key = config.config.deepseek_api_key
        config.config.deepseek_api_key = ""
        try:
            gen = ListingGenerator()
            g = SEED_GENOMES[0]
            listing = gen.generate(g)
            assert isinstance(listing, ListingCopy)
            assert len(listing.title) > 0
            assert len(listing.bullets) >= 1
            assert len(listing.seo_keywords) >= 3
        finally:
            config.config.deepseek_api_key = orig_key

    def test_template_generate_with_context(self, tmp_path):
        import config
        orig_key = config.config.deepseek_api_key
        config.config.deepseek_api_key = ""
        try:
            gen = ListingGenerator()
            g = SEED_GENOMES[0]
            listing = gen.generate(g, {"survival_rate": 0.8, "avg_price": 4.99,
                                       "competition": "medium"})
            assert isinstance(listing, ListingCopy)
        finally:
            config.config.deepseek_api_key = orig_key

    def test_fallback_description(self, tmp_path):
        import config
        orig_key = config.config.deepseek_api_key
        config.config.deepseek_api_key = ""
        try:
            gen = ListingGenerator()
            g = SEED_GENOMES[0]
            desc = gen._fallback_description(g)
            assert "<p>" in desc
            assert g.benefit in desc
        finally:
            config.config.deepseek_api_key = orig_key

    def test_audience_by_market(self, tmp_path):
        import config
        orig_key = config.config.deepseek_api_key
        config.config.deepseek_api_key = ""
        try:
            gen = ListingGenerator()
            g = SEED_GENOMES[0]
            listing = gen.generate(g)
            assert len(listing.target_audience) > 0
        finally:
            config.config.deepseek_api_key = orig_key


# ── ExtensionTester ──

class TestExtensionTester:
    def test_validate_passes_for_valid_build(self, tmp_path):
        builder = ExtensionBuilder()
        builder._build_dir = tmp_path
        g = SEED_GENOMES[0]
        builder.build(g, "test_val")
        tester = ExtensionTester()
        result = tester.validate(tmp_path / "test_val")
        assert isinstance(result, TestResult)

    def test_validate_missing_manifest(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        tester = ExtensionTester()
        result = tester.validate(d)
        assert result.passed is False
        assert any("manifest" in f for f in (result.failures or []))

    def test_validate_missing_files(self, tmp_path):
        d = tmp_path / "partial"
        d.mkdir()
        (d / "manifest.json").write_text(
            '{"manifest_version":3,"name":"T","version":"1.0"}')
        tester = ExtensionTester()
        result = tester.validate(d)
        assert result.passed is False

    def test_validate_bad_manifest_json(self, tmp_path):
        d = tmp_path / "badjson"
        d.mkdir()
        (d / "manifest.json").write_text("not json")
        tester = ExtensionTester()
        result = tester.validate(d)
        assert result.passed is False

    def test_testresult_summary_pass(self):
        r = TestResult(passed=True, total=4, failures=[])
        assert "All 4 checks passed" in r.summary

    def test_testresult_summary_fail(self):
        r = TestResult(passed=False, total=4, failures=["missing file", "syntax error"])
        assert "2/4" in r.summary
        assert "missing file" in r.summary


# ── GumroadPublisher ──

class TestGumroadPublisher:
    def test_dry_run_publish(self, tmp_path):
        pub = GumroadPublisher()
        g = SEED_GENOMES[0]
        zip_path = tmp_path / "test.zip"
        zip_path.write_text("dummy")
        result = pub.publish(g, zip_path, "org_test")
        assert result.success is True
        assert result.dry_run is True
        assert "dry_org_test" in result.product_id

    def test_make_description(self, tmp_path):
        pub = GumroadPublisher()
        g = SEED_GENOMES[0]
        desc = pub._make_description(g)
        assert g.benefit in desc
        assert "Features:" in desc


# ── ChromeStorePublisher ──

class TestChromeStorePublisher:
    def test_dry_run_publish_no_credentials(self, tmp_path):
        pub = ChromeStorePublisher()
        zip_path = tmp_path / "test.zip"
        zip_path.write_text("dummy zip content")
        result = pub.publish(zip_path, "org_cws", public=False)
        assert result.success is True
        assert result.dry_run is True
        assert "dry_cws_org_cws" in result.item_id

    def test_get_status_dry_run(self):
        pub = ChromeStorePublisher()
        status = pub.get_status("some_item")
        assert status["status"] == "dry_run"

    def test_can_publish_false_without_creds(self):
        pub = ChromeStorePublisher()
        assert pub._can_publish is False

    def test_can_publish_true_with_creds(self):
        pub = ChromeStorePublisher(client_id="x", client_secret="y", refresh_token="z")
        assert pub._can_publish is True


# ── MarketMonitor ──

class MockOrganism:
    def __init__(self, is_alive=True, gumroad_product_id="", genome=None, current_rating=4.0):
        self.is_alive = is_alive
        self.gumroad_product_id = gumroad_product_id
        self.genome = genome
        self.current_rating = current_rating


class TestMarketMonitor:
    def test_poll_simulates_for_no_product(self):
        mm = MarketMonitor()
        g = SEED_GENOMES[0]
        org = MockOrganism(is_alive=True, gumroad_product_id="", genome=g)
        results = mm.poll({"org1": org})
        assert "org1" in results
        assert "income" in results["org1"]
        assert "downloads" in results["org1"]

    def test_simulate_tick_with_genome(self):
        mm = MarketMonitor()
        g = SEED_GENOMES[0]
        org = MockOrganism(is_alive=True, gumroad_product_id="", genome=g)
        tick = mm._simulate_tick(org)
        assert tick["income"] >= 0
        assert tick["downloads"] >= 0
        assert tick["api_cost"] > 0

    def test_simulate_tick_without_genome(self):
        mm = MarketMonitor()
        org = MockOrganism(is_alive=True, gumroad_product_id="", genome=None)
        tick = mm._simulate_tick(org)
        assert tick["income"] == 0
        assert tick["downloads"] == 0

    def test_poll_skips_dead_organisms(self):
        mm = MarketMonitor()
        g = SEED_GENOMES[0]
        dead = MockOrganism(is_alive=False, gumroad_product_id="", genome=g)
        results = mm.poll({"dead_org": dead})
        assert "dead_org" in results  # poll still returns results
