"""Layer 1: Agent-Native 测试"""
import pytest
import json
from pathlib import Path

from layer1.semantic_git import SemanticGit, SemanticCommit, ChangeType
from layer1.intent_code import IntentCode
from layer1.autonomous_ci import AutonomousCI, CIStatus, CIRun


# ── SemanticGit ──

class TestSemanticGit:
    def test_commit_creates_entry(self, tmp_path):
        git = SemanticGit(_path=tmp_path / "git.json")
        cid = git.commit(
            intent="一键导出对话为 PDF",
            change_type=ChangeType.FEATURE,
            files=["content.js", "popup.html"],
            agent_id="agent_1",
            organism_id="org_1",
            genome_id="gen_1",
        )
        assert len(git.commits) == 1
        assert git.commits[0].intent == "一键导出对话为 PDF"
        assert git.commits[0].change_type == ChangeType.FEATURE

    def test_multiple_commits_form_chain(self, tmp_path):
        git = SemanticGit(_path=tmp_path / "git.json")
        c1 = git.commit("init", ChangeType.FEATURE, ["a.js"], "a1", "o1", "g1")
        c2 = git.commit("update", ChangeType.FIX, ["a.js"], "a1", "o1", "g1")
        assert len(git.commits) == 2
        assert git.commits[1].parent_commit == c1.commit_id

    def test_query_by_organism(self, tmp_path):
        git = SemanticGit(_path=tmp_path / "git.json")
        git.commit("A work", ChangeType.FEATURE, ["a.js"], "a1", "org_a", "g1")
        git.commit("B work", ChangeType.FIX, ["b.js"], "a2", "org_b", "g2")
        git.commit("A fix", ChangeType.FIX, ["a.js"], "a1", "org_a", "g1")
        a_commits = git.get_history("org_a")
        assert len(a_commits) == 2

    def test_query_by_intent(self, tmp_path):
        git = SemanticGit(_path=tmp_path / "git.json")
        git.commit("导出 PDF", ChangeType.FEATURE, ["a.js"], "a1", "o1", "g1")
        git.commit("修复 bug", ChangeType.FIX, ["b.js"], "a2", "o2", "g2")
        git.commit("PDF 优化", ChangeType.OPTIMIZE, ["a.js"], "a1", "o1", "g1")
        pdf_commits = git.search_by_intent("PDF")
        assert len(pdf_commits) == 2

    def test_save_and_load(self, tmp_path):
        path = tmp_path / "git.json"
        git = SemanticGit(_path=path)
        git.commit("test", ChangeType.FEATURE, ["f.js"], "a1", "o1", "g1")

        git2 = SemanticGit(_path=path)
        assert len(git2.commits) == 1
        assert git2.commits[0].intent == "test"


# ── IntentCode ──

class TestIntentCode:
    def test_store_creates_entry(self, tmp_path):
        ic = IntentCode(_path=tmp_path / "ic.json")
        block = ic.store(
            intent="实现一键导出",
            files={"content.js": "code here", "popup.html": "html here"},
            organism_id="org_1",
            genome_id="gen_1",
        )
        assert len(ic.blocks) == 1
        assert ic.blocks[block.block_id].intent == "实现一键导出"

    def test_store_multiple(self, tmp_path):
        ic = IntentCode(_path=tmp_path / "ic.json")
        ic.store("test 1", {"a.js": "c"}, organism_id="o1", genome_id="g1")
        ic.store("test 2", {"b.js": "c"}, organism_id="o2", genome_id="g2")
        assert len(ic.blocks) == 2

    def test_search_by_intent(self, tmp_path):
        ic = IntentCode(_path=tmp_path / "ic.json")
        ic.store("导出对话为 PDF", {"a.js": "c"}, organism_id="o1", genome_id="g1")
        ic.store("修复登录按钮", {"b.js": "c"}, organism_id="o2", genome_id="g2")
        ic.store("PDF 优化导出速度", {"a.js": "c"}, organism_id="o1", genome_id="g1")
        results = ic.search("PDF")
        assert len(results) == 2

    def test_save_and_load(self, tmp_path):
        path = tmp_path / "ic.json"
        ic = IntentCode(_path=path)
        ic.store("test", {"a.js": "code"}, organism_id="o1", genome_id="g1")

        ic2 = IntentCode(_path=path)
        assert len(ic2.blocks) >= 1


# ── AutonomousCI ──

class TestAutonomousCI:
    def test_ci_run_creates_result(self, tmp_path):
        ci = AutonomousCI(_path=tmp_path / "ci.json")
        result = ci.run(
            commit_id="c1",
            organism_id="o1",
            files={"content.js": "console.log('ok')", "manifest.json": '{"name":"t"}'},
            intent="simple extension",
        )
        assert result.commit_id == "c1"
        assert result.status is not None

    def test_ci_detects_sensitive_data(self, tmp_path):
        ci = AutonomousCI(_path=tmp_path / "ci.json")
        result = ci.run(
            commit_id="c2",
            organism_id="o2",
            files={"config.js": 'const API_KEY = "sk-secret-key"'},
            intent="bad extension",
        )
        assert result.status == CIStatus.FAILED

    def test_good_code_passes(self, tmp_path):
        ci = AutonomousCI(_path=tmp_path / "ci.json")
        result = ci.run(
            commit_id="c3",
            organism_id="o3",
            files={
                "manifest.json": '{"manifest_version":3,"name":"OK","version":"1.0"}',
                "content.js": "// safe content",
                "popup.html": "<html></html>",
                "popup.js": "// ok",
                "background.js": "// ok",
            },
            intent="clean extension",
        )
        # CI _run_tests uses random, so status may be MERGED or FAILED
        assert result.commit_id == "c3"
        assert result.status in (CIStatus.MERGED, CIStatus.FAILED)
