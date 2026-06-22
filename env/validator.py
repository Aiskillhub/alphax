"""产物验证器

在部署前验证生成的 Build 是否可用。
检查文件完整性、安全性、基本功能。
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class ValidationStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class ValidationResult:
    build_id: str
    status: ValidationStatus
    checks: list[dict] = field(default_factory=list)
    score: float = 0.0
    summary: str = ""
    validated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Validator:
    """验证生成的产物"""

    def validate(self, build) -> ValidationResult:
        """对 Build 运行所有验证检查"""
        checks = []

        # 1. 文件存在
        checks += self._check_files(build)

        # 2. HTML 有效性
        checks += self._check_html(build)

        # 3. JS 语法
        checks += self._check_javascript(build)

        # 4. Python 语法
        checks += self._check_python(build)

        # 5. 安全检查
        checks += self._check_security(build)

        # 6. 大小检查
        checks += self._check_size(build)

        # 计算分数
        passed = sum(1 for c in checks if c["status"] == "pass")
        failed = sum(1 for c in checks if c["status"] == "fail")
        score = passed / max(1, len(checks))

        if failed > 0:
            status = ValidationStatus.FAIL
        elif score < 0.8:
            status = ValidationStatus.WARN
        else:
            status = ValidationStatus.PASS

        return ValidationResult(
            build_id=build.build_id,
            status=status,
            checks=checks,
            score=round(score, 2),
            summary=f"{passed}/{len(checks)} checks passed, {failed} failed",
        )

    def _check_files(self, build) -> list[dict]:
        checks = []
        if not build.files:
            checks.append({"check": "files_exist", "status": "fail",
                          "detail": "No files in build"})
            return checks
        checks.append({"check": "files_exist", "status": "pass",
                      "detail": f"{len(build.files)} files"})

        has_readme = any(f.lower() == 'readme.md' for f in build.files)
        checks.append({"check": "has_readme", "status": "pass" if has_readme else "warn",
                      "detail": "README present" if has_readme else "Missing README.md"})

        has_index = any(f.lower() == 'index.html' for f in build.files)
        has_main = has_index or any(f.endswith('.py') for f in build.files)
        checks.append({"check": "has_entry_point", "status": "pass" if has_main else "fail",
                      "detail": "Entry point found" if has_main else "No entry point (index.html or .py)"})
        return checks

    def _check_html(self, build) -> list[dict]:
        checks = []
        for fname, content in build.files.items():
            if not fname.endswith('.html'):
                continue
            content_s = content if isinstance(content, str) else str(content)
            issues = []
            if '<!DOCTYPE html>' not in content_s and '<!doctype html>' not in content_s.lower():
                issues.append("missing DOCTYPE")
            if '</html>' not in content_s:
                issues.append("missing </html>")
            if '</body>' not in content:
                issues.append("missing </body>")
            checks.append({
                "check": f"html_valid:{fname}",
                "status": "fail" if issues else "pass",
                "detail": "; ".join(issues) if issues else "HTML structure valid",
            })
        if not checks:
            checks.append({"check": "html_check", "status": "pass", "detail": "No HTML files"})
        return checks

    def _check_javascript(self, build) -> list[dict]:
        checks = []
        for fname, content in build.files.items():
            if not fname.endswith('.js'):
                continue
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                    f.write(content)
                    f.flush()
                    result = subprocess.run(
                        ['node', '--check', f.name],
                        capture_output=True, text=True, timeout=10,
                    )
                    checks.append({
                        "check": f"js_syntax:{fname}",
                        "status": "pass" if result.returncode == 0 else "fail",
                        "detail": result.stderr.strip()[:200] if result.returncode != 0 else "JS syntax OK",
                    })
            except FileNotFoundError:
                checks.append({"check": f"js_syntax:{fname}", "status": "warn",
                              "detail": "Node not available, skipped JS check"})
            except Exception:
                checks.append({"check": f"js_syntax:{fname}", "status": "warn",
                              "detail": "JS check failed to run"})
        if not checks:
            checks.append({"check": "js_check", "status": "pass", "detail": "No JS files"})
        return checks

    def _check_python(self, build) -> list[dict]:
        checks = []
        for fname, content in build.files.items():
            if not fname.endswith('.py'):
                continue
            try:
                compile(content, fname, 'exec')
                checks.append({"check": f"py_syntax:{fname}", "status": "pass",
                              "detail": "Python syntax OK"})
            except SyntaxError as e:
                checks.append({"check": f"py_syntax:{fname}", "status": "fail",
                              "detail": f"Syntax error: {e}"})
        if not checks:
            checks.append({"check": "py_check", "status": "pass", "detail": "No Python files"})
        return checks

    def _check_security(self, build) -> list[dict]:
        checks = []
        sensitive_patterns = [
            ('API_KEY', 'hardcoded API key'),
            ('SECRET', 'hardcoded secret'),
            ('password', 'hardcoded password'),
            ('token', 'hardcoded token'),
        ]
        for fname, content in build.files.items():
            content_s = content if isinstance(content, str) else str(content)
            findings = []
            for pattern, desc in sensitive_patterns:
                if pattern in content_s.lower():
                    # Check if it's an assignment (not just a comment)
                    lines = [l for l in content_s.split('\n')
                            if pattern in l.lower()
                            and ('=' in l or ':' in l)
                            and not l.strip().startswith('//')
                            and not l.strip().startswith('#')]
                    if lines:
                        findings.append(desc)
            if findings:
                checks.append({"check": f"security:{fname}", "status": "warn",
                              "detail": f"Possible: {', '.join(findings)}"})
        if not checks:
            checks.append({"check": "security", "status": "pass", "detail": "No obvious secrets"})
        return checks

    def _check_size(self, build) -> list[dict]:
        checks = []
        total_size = sum(len(c) for c in build.files.values())
        if total_size > 1_000_000:
            checks.append({"check": "size", "status": "warn",
                          "detail": f"Large build: {total_size / 1000:.0f}KB"})
        elif total_size < 100:
            checks.append({"check": "size", "status": "fail",
                          "detail": f"Too small: {total_size}B — likely incomplete"})
        else:
            checks.append({"check": "size", "status": "pass",
                          "detail": f"Build size: {total_size / 1000:.1f}KB"})
        return checks
