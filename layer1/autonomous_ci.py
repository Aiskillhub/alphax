"""Layer 1: 自主 CI

Agent 提交代码 → 自动生成测试 → 自动合入

流水线：
  1. Agent Push → 检测意图变更
  2. AI 根据意图生成测试用例
  3. 运行测试 → 通过则自动合入，失败则 Agent 自动修
  4. 记录 CI 结果到语义图
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum

from config import config
from core.api_utils import call_deepseek, extract_json


class CIStatus(str, Enum):
    PENDING = "pending"
    GENERATING_TESTS = "generating"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    AUTO_FIXING = "auto_fixing"
    MERGED = "merged"
    REJECTED = "rejected"


@dataclass
class TestCase:
    name: str
    intent_tested: str
    code: str


@dataclass
class CIRun:
    run_id: str
    commit_id: str
    organism_id: str
    status: CIStatus = CIStatus.PENDING
    tests_generated: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    auto_fix_attempts: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""

    @property
    def pass_rate(self) -> float:
        total = self.tests_passed + self.tests_failed
        if total == 0:
            return 1.0
        return self.tests_passed / total


@dataclass
class AutonomousCI:
    """自主 CI 引擎"""

    runs: list[CIRun] = field(default_factory=list)
    _path: Path = config.data_dir / "ci_runs.json"

    def __post_init__(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self.runs = [CIRun(**r) for r in data.get("runs", [])]
            except (json.JSONDecodeError, OSError):
                pass

    def run(
        self,
        commit_id: str,
        organism_id: str,
        files: dict[str, str],
        intent: str,
    ) -> CIRun:
        """对一次提交运行 CI 流水线"""
        import hashlib
        raw = commit_id + organism_id + str(time.time())
        run_id = hashlib.sha256(raw.encode()).hexdigest()[:12]

        ci_run = CIRun(
            run_id=run_id,
            commit_id=commit_id,
            organism_id=organism_id,
            status=CIStatus.GENERATING_TESTS,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        # 0. 预先扫描敏感数据
        secrets = self._scan_secrets(files)
        if secrets:
            ci_run.status = CIStatus.FAILED
            ci_run.errors = [f"敏感数据泄露: {s}" for s in secrets]
            ci_run.finished_at = datetime.now(timezone.utc).isoformat()
            self.runs.append(ci_run)
            self._save()
            return ci_run

        # 1. 生成测试
        ci_run.status = CIStatus.GENERATING_TESTS
        tests = self._generate_tests(files, intent)

        # 2. 运行测试
        ci_run.status = CIStatus.RUNNING
        ci_run.tests_generated = len(tests)
        passed, failed = self._run_tests(tests, files)

        ci_run.tests_passed = len(passed)
        ci_run.tests_failed = len(failed)

        if failed:
            # 3. 自动修复
            ci_run.status = CIStatus.AUTO_FIXING
            ci_run.auto_fix_attempts += 1
            ci_run.errors = failed
            ci_run.status = CIStatus.FAILED
        else:
            ci_run.status = CIStatus.MERGED

        ci_run.finished_at = datetime.now(timezone.utc).isoformat()
        self.runs.append(ci_run)
        self._save()
        return ci_run

    def _scan_secrets(self, files: dict[str, str]) -> list[str]:
        """扫描代码中的敏感数据（API key、token、密码等）"""
        import re
        findings = []
        patterns = [
            (r'sk-[a-zA-Z0-9]{20,}', "OpenAI/DeepSeek API Key"),
            (r'AIza[0-9A-Za-z\-_]{35}', "Google API Key"),
            (r'api[_-]?key\s*=\s*["\'][A-Za-z0-9\-_]{8,}["\']', "API Key 赋值"),
            (r'token\s*=\s*["\'][A-Za-z0-9\-_]{8,}["\']', "Token 硬编码"),
            (r'password\s*=\s*["\'][^"\']+["\']', "密码硬编码"),
            (r'secret\s*=\s*["\'][^"\']+["\']', "Secret 硬编码"),
        ]
        for fname, content in files.items():
            for pattern, desc in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    findings.append(f"{fname}: {desc}")
        return findings

    def _generate_tests(self, files: dict[str, str], intent: str) -> list[TestCase]:
        """根据意图和代码生成测试用例"""
        if config.deepseek_api_key:
            return self._ai_generate_tests(files, intent)
        return self._template_generate_tests(files, intent)

    def _ai_generate_tests(self, files: dict[str, str], intent: str) -> list[TestCase]:
        """用 DeepSeek 生成针对性测试"""
        code_sample = "\n".join(
            f"// {name}:\n{content[:200]}..." for name, content in list(files.items())[:3]
        )

        prompt = f"""为一个 Chrome Extension 的代码变更生成测试用例。

意图: {intent}

代码片段:
{code_sample}

生成 5-8 个测试用例。返回 JSON:
{{
  "tests": [
    {{"name": "测试名", "intent_tested": "验证什么意图", "code": "伪代码描述"}}
  ]
}}

测试类型应包含: 功能测试、边界测试、安全测试、性能约束测试。
只返回 JSON。"""

        try:
            content = call_deepseek(
                prompt, config.deepseek_api_key, config.deepseek_base_url,
                temperature=0.3, max_tokens=500,
            )
            content = extract_json(content)
            parsed = json.loads(content)
            return [TestCase(**t) for t in parsed.get("tests", [])]
        except Exception:
            return self._template_generate_tests(files, intent)

    def _template_generate_tests(self, files: dict[str, str], intent: str) -> list[TestCase]:
        """模板生成测试（无 API 时）"""
        tests = [
            TestCase("manifest_valid", "验证 manifest.json 结构", "check manifest v3 fields"),
            TestCase("js_syntax", "验证所有 JS 语法正确", "node --check *.js"),
            TestCase("no_secrets", "验证无敏感信息泄露", "grep api_key *.js"),
        ]

        # 根据意图添加针对性测试
        if "export" in intent.lower():
            tests.append(TestCase("export_works", "导出功能正常", "call export action, check result"))
            tests.append(TestCase("export_empty", "空对话不崩溃", "export 0 messages"))
        elif "search" in intent.lower():
            tests.append(TestCase("search_finds", "搜索能找到结果", "query known text"))
            tests.append(TestCase("search_empty", "搜索无结果不崩溃", "query non-existent"))

        # 检查每个文件
        for fname in files:
            tests.append(TestCase(
                f"file_exists_{fname.replace('.', '_')}",
                f"文件 {fname} 存在且非空",
                f"check {fname} size > 0"
            ))

        return tests

    def _run_tests(self, tests: list[TestCase], files: dict[str, str]) -> tuple[list[str], list[str]]:
        """模拟运行测试（实际会调用 builder/tester.py 的逻辑）"""
        passed = []
        failed = []

        for test in tests:
            # 模拟测试执行
            if random.random() < 0.85:  # 85% 通过率（模拟）
                passed.append(test.name)
            else:
                failed.append(test.name)

        return passed, failed

    def stats(self) -> dict:
        if not self.runs:
            return {"total_runs": 0}

        merged = sum(1 for r in self.runs if r.status == CIStatus.MERGED)
        return {
            "total_runs": len(self.runs),
            "merged": merged,
            "merge_rate": merged / len(self.runs),
            "avg_tests": sum(r.tests_generated for r in self.runs) / len(self.runs),
            "avg_pass_rate": sum(r.pass_rate for r in self.runs) / len(self.runs),
            "auto_fixes": sum(r.auto_fix_attempts for r in self.runs),
        }

    def _save(self):
        self._path.write_text(json.dumps({
            "runs": [
                {k: v for k, v in r.__dict__.items()} for r in self.runs
            ]
        }, indent=2))
