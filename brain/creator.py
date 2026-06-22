"""多 LLM 代码生成器

不是模板填充。传入完整需求描述，不同 LLM 产出真正不同的代码。
Genome 表达为 prompt → LLM 生成完整代码 → 返回 Build。
"""

from __future__ import annotations

import json
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class Build:
    """一次代码生成的产物"""
    build_id: str = ""
    organism_id: str = ""
    llm_backend: str = "deepseek"
    prompt_strategy: str = ""
    files: dict[str, str] = field(default_factory=dict)  # filename → content
    generated_at: str = ""

    def __post_init__(self):
        if not self.build_id:
            self.build_id = hashlib.sha256(
                f"{self.organism_id}{time.time()}".encode()
            ).hexdigest()[:12]
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()


@dataclass
class Creator:
    """根据 Genome 生成代码

    支持多个 LLM 后端。每个 organism 的 genome 锁定一个 LLM 后端，
    不同后端的代码风格和架构真正不同。
    """

    model: str = "deepseek-chat"
    max_tokens: int = 16000
    build_dir: Path = config.data_dir / "builds"
    _token_usage: dict[str, int] = field(default_factory=dict)
    require_llm: bool = True  # 设为 False 则允许模板降级

    def generate(self, organism, strategy: str = "") -> Build:
        """从 organism 的 genome 生成代码"""
        genome = organism.genome
        if not genome:
            return Build(organism_id=organism.organism_id)

        prompt = self._genome_to_prompt(genome, strategy)
        llm_backend = getattr(genome, 'llm_backend', 'deepseek') if hasattr(genome, 'llm_backend') else 'deepseek'

        if self.require_llm and not config.has_llm:
            raise RuntimeError(
                "Creator.require_llm=True 但 DEEPSEEK_API_KEY 未设置。"
                "设置环境变量 DEEPSEEK_API_KEY 或设 Creator(require_llm=False)"
            )

        try:
            files = self._call_llm(prompt, llm_backend)
        except Exception as e:
            import logging
            logger = logging.getLogger("creator")
            logger.warning(f"LLM call failed, falling back to rule-based generation: {e}")
            files = self._fallback_generate(genome)

        build = Build(
            organism_id=organism.organism_id,
            llm_backend=llm_backend,
            prompt_strategy=strategy or getattr(genome, 'prompt_strategy', 'default'),
            files=files,
        )

        # Write to disk
        self._write_build(build)
        return build

    def _genome_to_prompt(self, genome, strategy: str = "") -> str:
        """基因组 → 代码生成 prompt（精简版）"""
        cat = getattr(genome, 'category', 'dev_tools')
        ptype = getattr(genome, 'product_type', 'web_tool')
        style = getattr(genome, 'design_style', 'minimal') if hasattr(genome, 'design_style') else 'minimal'
        complexity = getattr(genome, 'code_complexity', 'standard') if hasattr(genome, 'code_complexity') else 'standard'
        is_agent = ptype in ("chrome_extension", "api_service", "web_tool")
        runtime = 'mcp' if ptype == 'api_service' else 'web' if ptype == 'web_tool' else 'chrome_extension'

        lines = [
            f"Build a {style} {ptype} ({cat}, ${getattr(genome, 'price_point', 4.99)}). "
            + ("Single HTML file." if complexity == 'minimal' else "Multi-file project." if complexity == 'standard' else "Full project with tests."),
        ]

        if strategy:
            lines[0] += f" Strategy: {strategy}"

        if is_agent:
            lines.extend([
                "",
                "## Agent Packaging (REQUIRED)",
                "Include agent.json + server.js. server.js = MCP JSON-RPC server over stdin/stdout:",
                "readline → parse JSON-RPC → handle initialize/tools_list/tools_call → stdout.write response.",
                f"agent.json: {{\"name\":\"kebab-case\",\"version\":\"1.0.0\",\"runtime\":\"{runtime}\",\"entry\":\"server.js\",\"tools\":[...]}}",
            ])

        lines.extend([
            "",
            "Return JSON: {\"filename\":\"content\",...}. Valid JSON only.",
        ])

        return "\n".join(lines)

    def _call_llm(self, prompt: str, backend: str = "deepseek") -> dict[str, str]:
        """调用 LLM 生成代码"""
        import urllib.request

        model = config.deepseek_model

        body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a senior software engineer. You generate complete, working code. Output only valid JSON with filenames as keys and complete file contents as values."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
            "max_tokens": self.max_tokens,
        }).encode()

        base = config.deepseek_base_url.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        url = f"{base}/chat/completions"

        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {config.deepseek_api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body_text = e.read().decode()[:500] if e.fp else ""
            raise RuntimeError(
                f"API {e.code} from {url}: {e.reason}. body: {body_text}"
            ) from e

        # Track token usage
        usage = data.get("usage", {})
        self._token_usage[backend] = self._token_usage.get(backend, 0) + usage.get("total_tokens", 0)

        content = data["choices"][0]["message"]["content"]
        candidates = []

        # 1. 直接是 JSON
        candidates.append(content.strip())

        # 2. 被 ```json ... ``` 包裹
        if "```json" in content:
            block = content.split("```json", 1)[1]
            if "```" in block:
                candidates.append(block.split("```", 1)[0].strip())

        # 3. 被 ``` ... ``` 包裹（无语言标记）
        if "```" in content:
            parts = content.split("```")
            for i in range(1, len(parts), 2):
                candidates.append(parts[i].strip())

        # 4. 提取 {...} 块
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            candidates.append(content[start:end + 1])

        for raw in candidates:
            if not raw or not raw.startswith("{"):
                continue
            # 尝试直接解析
            try:
                return self._normalize_files(json.loads(raw))
            except json.JSONDecodeError:
                pass
            # 修复常见问题后重试
            try:
                fixed = self._repair_json(raw)
                return self._normalize_files(json.loads(fixed))
            except json.JSONDecodeError:
                continue

        # All parse attempts failed — log and return a minimal fallback
        import logging
        logger = logging.getLogger("creator")
        logger.warning(f"JSON parse failed for all candidates (content length: {len(content)}), using fallback")
        fallback = self._brute_force_extract(content)
        if fallback:
            return self._normalize_files(fallback)
        # Absolute last resort: return a minimal HTML page
        return {"index.html": "<!DOCTYPE html>\n<html><head><title>Generated</title></head><body><h1>Generated Tool</h1><p>Auto-generated by AlphaX.</p></body></html>"}

    @staticmethod
    def _normalize_files(files: dict) -> dict[str, str]:
        """确保所有 file content 都是字符串"""
        result = {}
        for k, v in files.items():
            if isinstance(v, dict):
                result[k] = json.dumps(v, indent=2)
            elif isinstance(v, list):
                result[k] = json.dumps(v, indent=2)
            elif not isinstance(v, str):
                result[k] = str(v)
            else:
                result[k] = v
        return result

    @staticmethod
    def _repair_json(raw: str) -> str:
        """修复常见 LLM JSON 输出问题，包括 token 截断"""
        import re
        fixed = raw.strip()
        # Remove BOM or invisible chars at start
        fixed = fixed.lstrip("﻿")
        # If the last character is mid-string (truncated), drop the incomplete line
        if fixed and fixed[-1] not in ("}", "]", '"', "\n"):
            last_nl = fixed.rfind("\n")
            if last_nl > 100:
                fixed = fixed[:last_nl]
        fixed = fixed.rstrip(",\n ")
        # Odd quote count → string not closed
        if fixed.count('"') % 2 != 0:
            fixed += '"'
        # Balance braces and brackets
        for pair in [("{", "}"), ("[", "]")]:
            diff = fixed.count(pair[0]) - fixed.count(pair[1])
            if diff > 0:
                fixed += pair[1] * diff
        # Remove trailing commas (including after nested structures)
        fixed = re.sub(r",\s*}", "}", fixed)
        fixed = re.sub(r",\s*]", "]", fixed)
        # Fix missing commas between adjacent string values
        # "key1": "v1"\n"key2": → "key1": "v1",\n"key2":
        fixed = re.sub(r'"\s*\n\s*"', '",\n"', fixed)
        return fixed

    @staticmethod
    def _brute_force_extract(raw: str) -> dict[str, str] | None:
        """Last resort: regex-extract filename→content pairs when JSON is malformed"""
        import re
        files = {}
        # Match top-level "filename.ext": "..." pairs (handle escaped quotes in content)
        # Find all "key": "value" at the top level (key contains a file extension)
        pattern = re.compile(
            r'"([a-zA-Z0-9_\-./]+\.(?:html|css|js|py|json|md|txt|svg|png|yaml|yml|toml|xml))"\s*:\s*"',
        )
        pos = 0
        matches = list(pattern.finditer(raw))
        for i, m in enumerate(matches):
            fname = m.group(1)
            val_start = m.end()
            # Find the closing unescaped quote
            j = val_start
            while j < len(raw):
                ch = raw[j]
                if ch == '\\' and j + 1 < len(raw):
                    j += 2  # skip escaped char
                    continue
                if ch == '"':
                    # Check if next non-space is , or }
                    after = raw[j+1:j+10].strip() if j+1 < len(raw) else ""
                    if not after or after[0] in (',', '}', '\n'):
                        content = raw[val_start:j]
                        # Unescape JSON escapes
                        content = content.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
                        files[fname] = content
                        pos = j + 1
                        break
                j += 1
        return files if files else None

    def _fallback_generate(self, genome) -> dict[str, str]:
        """LLM 不可用时的基础生成"""
        cat = str(getattr(genome, 'category', 'dev_tools'))
        ptype = str(getattr(genome, 'product_type', 'web_tool'))
        name = genome.express() if hasattr(genome, 'express') else "Digital Tool"
        slug = name.lower().replace(" ", "-").replace("_", "-")
        is_agent = ptype in ("chrome_extension", "api_service", "web_tool")

        result = {
            "index.html": f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name}</title>
<style>
:root{{--bg:#fafafa;--card:#fff;--border:#e5e7eb;--text:#111;--muted:#6b7280;--accent:#6366f1}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);max-width:800px;margin:0 auto;padding:40px 20px}}
h1{{font-size:24px;margin-bottom:8px}}
p{{color:var(--muted);margin-bottom:24px}}
.tool{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px}}
textarea{{width:100%;height:200px;border:1px solid var(--border);border-radius:8px;padding:12px;font-family:monospace;resize:vertical}}
button{{padding:10px 24px;background:var(--accent);color:#fff;border:none;border-radius:8px;cursor:pointer;margin-top:12px}}
</style>
</head>
<body>
<h1>{name}</h1>
<p>AI-generated {cat} tool. Category: {cat}</p>
<div class="tool">
  <textarea placeholder="Enter your input here..."></textarea>
  <button>Process</button>
</div>
<p style="margin-top:24px;font-size:12px;color:var(--muted)">Built by Alpha X Evolution Engine</p>
</body>
</html>""",
            "README.md": f"# {name}\n\nAI-generated {cat} tool.\n\n## Usage\n\nOpen index.html in a browser.\n",
        }

        if is_agent:
            runtime = "mcp" if ptype == "api_service" else "web" if ptype == "web_tool" else "chrome_extension"
            result["agent.json"] = json.dumps({
                "name": slug,
                "version": "1.0.0",
                "runtime": runtime,
                "entry": "server.js",
                "tools": [
                    {
                        "name": f"run_{slug.replace('-', '_')}",
                        "description": f"Execute the {name} agent",
                        "parameters": {"input": {"type": "string", "description": "Input data"}},
                    }
                ],
            }, indent=2)
            result["server.js"] = f"""#!/usr/bin/env node
// {name} — Alpha X Generated MCP Agent
const rl = require('readline').createInterface({{ input: process.stdin }});

rl.on('line', (line) => {{
  if (!line.trim()) return;
  const req = JSON.parse(line);
  const {{ id, method, params }} = req;

  const respond = (result) => process.stdout.write(JSON.stringify({{ jsonrpc: '2.0', id, result }}) + '\\n');
  const err = (code, msg) => process.stdout.write(JSON.stringify({{ jsonrpc: '2.0', id, error: {{ code, message: msg }} }}) + '\\n');

  if (method === 'initialize') {{
    respond({{ protocolVersion: '0.1.0', serverInfo: {{ name: '{slug}', version: '1.0.0' }}, capabilities: {{ tools: {{}} }} }});
  }} else if (method === 'tools/list') {{
    respond({{ tools: [{{ name: 'run_{slug.replace('-', '_')}', description: 'Execute {name}', inputSchema: {{ type: 'object', properties: {{ input: {{ type: 'string' }} }}, required: ['input'] }} }}] }});
  }} else if (method === 'tools/call') {{
    const args = params?.arguments || {{}};
    respond({{ ok: true, input: args.input, processed: true, agent: '{name}', generatedBy: 'Alpha X' }});
  }} else {{
    err(-32601, 'Unknown method: ' + method);
  }}
}});
process.stderr.write('{name} MCP Agent ready\\n');
"""

        return result

    def _write_build(self, build: Build):
        """将构建产物写入磁盘"""
        import os
        build_dir = self.build_dir / f"gen_{build.organism_id}"
        build_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in build.files.items():
            filepath = build_dir / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, dict):
                content = json.dumps(content, indent=2)
            elif not isinstance(content, str):
                content = str(content)
            filepath.write_text(content)
        # Also write a manifest
        (build_dir / "manifest.json").write_text(json.dumps({
            "build_id": build.build_id,
            "organism_id": build.organism_id,
            "llm_backend": build.llm_backend,
            "prompt_strategy": build.prompt_strategy,
            "files": list(build.files.keys()),
            "generated_at": build.generated_at,
        }, indent=2))
