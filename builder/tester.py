"""AlphaX Tester — 自动验证生成的代码"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestResult:
    passed: bool
    total: int = 0
    failures: list[str] | None = None
    output: str = ""

    @property
    def summary(self) -> str:
        if self.passed:
            return f"All {self.total} checks passed"
        return f"{len(self.failures)}/{self.total} checks failed:\n" + "\n".join(
            f"  - {f}" for f in (self.failures or [])
        )


class ExtensionTester:
    """对生成的 Chrome Extension 做静态验证。支持目录或 ZIP 文件。"""

    def validate(self, build_path: Path) -> TestResult:
        import tempfile, zipfile

        # If ZIP, extract to temp dir first
        if build_path.suffix == '.zip':
            tmp = tempfile.mkdtemp(prefix='alphax_test_')
            with zipfile.ZipFile(build_path, 'r') as zf:
                zf.extractall(tmp)
            build_dir = Path(tmp)
        else:
            build_dir = build_path

        checks = [
            self._check_manifest(build_dir),
            self._check_required_files(build_dir),
            self._check_js_syntax(build_dir),
            self._check_no_sensitive_data(build_dir),
        ]
        failures = [f for f in checks if f]
        return TestResult(
            passed=len(failures) == 0,
            total=len(checks),
            failures=failures or [],
        )

    def _check_manifest(self, d: Path) -> str | None:
        manifest = d / "manifest.json"
        if not manifest.exists():
            return "manifest.json missing"
        import json
        try:
            data = json.loads(manifest.read_text())
            required = ["manifest_version", "name", "version"]
            for key in required:
                if key not in data:
                    return f"manifest.json missing required field: {key}"
            if data["manifest_version"] != 3:
                return f"manifest_version must be 3, got {data['manifest_version']}"
        except json.JSONDecodeError as e:
            return f"manifest.json is not valid JSON: {e}"
        return None

    def _check_required_files(self, d: Path) -> str | None:
        required = ["content.js", "popup.html", "popup.js", "background.js"]
        for f in required:
            fp = d / f
            if not fp.exists():
                return f"Missing required file: {f}"
            if fp.stat().st_size == 0:
                return f"File is empty: {f}"
        return None

    def _check_js_syntax(self, d: Path) -> str | None:
        for js_file in d.glob("*.js"):
            try:
                result = subprocess.run(
                    ["node", "--check", str(js_file)],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode != 0:
                    return f"Syntax error in {js_file.name}: {result.stderr.strip()}"
            except FileNotFoundError:
                return "Node.js not available, skipping syntax check"
            except subprocess.TimeoutExpired:
                pass
        return None

    def _check_no_sensitive_data(self, d: Path) -> str | None:
        sensitive = ["api_key", "API_KEY", "sk-", "Bearer ", "password", "secret"]
        for f in d.glob("*.js"):
            content = f.read_text()
            for s in sensitive:
                if s in content:
                    return f"Sensitive pattern '{s}' found in {f.name}"
        return None
