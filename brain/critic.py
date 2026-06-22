"""对抗审查器

Creator 生成 → Critic 找 bug/模拟差评/检查质量
不通过 → 退回 Creator 修改（最多 3 轮）

这是 Layer 5 对抗自博弈的核心：Creator 和 Critic 同时进化。
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import urllib.request

from config import config


class ReviewVerdict(str, Enum):
    PASS = "pass"
    RETRY = "retry"       # 有 bug，需要修改
    REJECT = "reject"     # 从根本上不可行


@dataclass
class Issue:
    """一个发现的问题"""
    severity: str         # critical / major / minor / style
    file: str
    description: str
    suggestion: str = ""


@dataclass
class Review:
    """一次审查结果"""
    build_id: str
    verdict: ReviewVerdict
    issues: list[Issue] = field(default_factory=list)
    score: float = 0.0     # 0.0-1.0 质量分
    summary: str = ""
    reviewed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Critic:
    """审查 Creator 生成的产物

    三个维度：
    1. 能跑吗？（执行验证）
    2. 有 bug 吗？（静态分析 + LLM 审查）
    3. 用户会喜欢吗？（LLM 模拟用户视角）
    """

    max_retries: int = 3

    def review(self, build) -> Review:
        """审查一个构建产物"""
        issues = []

        # 1. 执行验证
        issues += self._validate_execution(build)

        # 2. 代码质量（LLM 审查或基础检查）
        issues += self._review_quality(build)

        # 3. 用户视角
        issues += self._review_user_experience(build)

        # 评分
        criticals = sum(1 for i in issues if i.severity == "critical")
        majors = sum(1 for i in issues if i.severity == "major")
        score = max(0.0, 1.0 - criticals * 0.4 - majors * 0.2 - len(issues) * 0.05)

        if criticals > 0:
            verdict = ReviewVerdict.REJECT
        elif majors > 2 or score < 0.5:
            verdict = ReviewVerdict.RETRY
        else:
            verdict = ReviewVerdict.PASS

        return Review(
            build_id=build.build_id,
            verdict=verdict,
            issues=issues,
            score=round(score, 2),
            summary=f"Score={score:.2f}, {len(issues)} issues ({criticals} critical, {majors} major)",
        )

    def _validate_execution(self, build) -> list[Issue]:
        """验证代码能否执行"""
        issues = []
        html_files = [f for f in build.files if f.endswith('.html')]
        js_files = [f for f in build.files if f.endswith('.js')]
        py_files = [f for f in build.files if f.endswith('.py')]

        # Check HTML files have basic structure
        for fname in html_files:
            content = build.files[fname]
            content_s = content if isinstance(content, str) else str(content)
            if '<!DOCTYPE html>' not in content_s and '<!doctype html>' not in content_s.lower():
                issues.append(Issue("major", fname, "Missing DOCTYPE declaration",
                                    "Add <!DOCTYPE html> at the beginning"))
            if '</html>' not in content_s:
                issues.append(Issue("critical", fname, "Missing closing </html> tag",
                                    "Ensure the HTML document is complete"))
            if '<script' in content and '</script>' not in content:
                issues.append(Issue("major", fname, "Unclosed <script> tag",
                                    "Check script tag syntax"))

        # Try executing Python files
        for fname in py_files:
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                    f.write(build.files[fname])
                    f.flush()
                    result = subprocess.run(
                        ['python3', '-c', f'compile(open("{f.name}").read(), "{fname}", "exec")'],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode != 0:
                        issues.append(Issue("critical", fname,
                                            f"Python syntax error: {result.stderr.strip()[:200]}",
                                            "Fix the syntax error"))
            except Exception as e:
                pass

        # Basic check: do files exist?
        if not build.files:
            issues.append(Issue("critical", "", "No files generated", "Generate at least one file"))
        if 'README.md' not in build.files:
            issues.append(Issue("minor", "", "Missing README.md", "Add a README with usage instructions"))

        return issues

    def _review_quality(self, build) -> list[Issue]:
        """代码质量审查（正则兜底，LLM 审查已单独调用）"""
        issues = []

        for fname, content in build.files.items():
            content_str = content if isinstance(content, str) else str(content)
            if 'TODO' in content_str or 'FIXME' in content_str:
                issues.append(Issue("minor", fname, "Contains TODO/FIXME comments",
                                    "Implement the missing functionality"))
            if 'console.log(' in content_str or 'print(' in content_str:
                issues.append(Issue("minor", fname, "Contains debug output",
                                    "Remove debug console.log/print statements"))
            if 'API_KEY' in content_str or 'SECRET' in content_str or 'password' in content_str.lower():
                if '= "' in content_str or "= '" in content_str:
                    issues.append(Issue("major", fname, "Possible hardcoded credential",
                                        "Use environment variables for secrets"))
            if fname.endswith('.html') and 'onclick=' in content_str:
                issues.append(Issue("minor", fname, "Inline event handlers detected",
                                    "Consider using addEventListener instead"))
        return issues

    def _llm_review(self, build) -> list[Issue]:
        """使用 LLM 深度审查代码：找逻辑 bug、架构问题、安全漏洞"""
        issues = []
        code_snippets = []
        for fname, content in build.files.items():
            # 限制每个文件长度，避免超 token
            truncated = content[:3000] + ("...[truncated]" if len(content) > 3000 else "")
            code_snippets.append(f"### {fname}\n```\n{truncated}\n```")

        if not code_snippets:
            return issues

        review_prompt = f"""Review the following code for a product called "{build.organism_id}".

{chr(10).join(code_snippets[:5])}

## Review Criteria
Find real issues. Be harsh but fair. Look for:
1. Logic bugs — will this actually work correctly?
2. Security issues — XSS, injection, exposed secrets
3. Architecture — is the code well-structured?
4. Completeness — are there placeholders or dead features?
5. UX problems — would a real user be confused or frustrated?
6. Performance — obvious inefficiencies

Return JSON:
{{"issues":[{{"severity":"critical|major|minor","file":"filename","description":"what's wrong","suggestion":"how to fix"}}]}}

Only report REAL issues. If code is genuinely good, return empty issues array."""

        try:
            body = json.dumps({
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "You are a strict code reviewer. Find real bugs and issues. Output only valid JSON."},
                    {"role": "user", "content": review_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 2000,
            }).encode()

            req = urllib.request.Request(
                f"{config.deepseek_base_url}/v1/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {config.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                content = data["choices"][0]["message"]["content"]
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    result = json.loads(content[start:end])
                    for item in result.get("issues", []):
                        issues.append(Issue(
                            severity=item.get("severity", "minor"),
                            file=item.get("file", ""),
                            description=item.get("description", ""),
                            suggestion=item.get("suggestion", ""),
                        ))
        except Exception:
            pass  # LLM 不可用时静默回退

        return issues

    def _review_user_experience(self, build) -> list[Issue]:
        """从用户角度审查"""
        issues = []
        html_files = [f for f in build.files if f.endswith('.html')]

        for fname in html_files:
            content = build.files[fname]
            if '<meta name="viewport"' not in content:
                issues.append(Issue("minor", fname,
                                    "Not mobile-responsive (missing viewport meta)",
                                    "Add <meta name='viewport' content='width=device-width,initial-scale=1'>"))
            if '<title>' not in content:
                issues.append(Issue("minor", fname, "Missing <title> tag", "Add a page title"))
            if '<h1>' not in content and '<h2>' not in content:
                issues.append(Issue("minor", fname, "No heading hierarchy", "Add h1/h2 for content structure"))

        return issues

    def should_retry(self, review: Review, attempt: int) -> bool:
        """判断是否应该重试"""
        if review.verdict == ReviewVerdict.PASS:
            return False
        if review.verdict == ReviewVerdict.REJECT:
            return False
        return attempt < self.max_retries

    def improvement_feedback(self, review: Review) -> str:
        """生成改进建议，传给 Creator 用于重试"""
        lines = ["## Improvements Needed", ""]
        for issue in review.issues:
            lines.append(f"- [{issue.severity.upper()}] {issue.file}: {issue.description}")
            if issue.suggestion:
                lines.append(f"  Fix: {issue.suggestion}")
        return "\n".join(lines)
