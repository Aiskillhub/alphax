"""工具自创生注册表

当 Reflector 发现重复手工动作时，自动生成工具脚本。
这些工具被持久化，后来者 organism 可以直接调用。
"""

from __future__ import annotations

import json
import subprocess
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config


@dataclass
class CreatedTool:
    """一个自创工具"""
    tool_id: str
    name: str
    description: str
    script_path: str = ""
    language: str = "python"
    capabilities: list[str] = field(default_factory=list)
    usage_count: int = 0
    success_rate: float = 1.0
    created_at: str = ""
    created_by: str = ""  # insight 来源

    def __post_init__(self):
        if not self.tool_id:
            self.tool_id = hashlib.sha256(
                f"{self.name}{self.created_at}".encode()
            ).hexdigest()[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class Toolkit:
    """自创工具注册表——工具创生层的持久化存储"""

    def __init__(self):
        self._registry_path = config.data_dir / "toolkit_registry.json"
        self._tools_dir = config.data_dir / "created_tools"
        self._tools_dir.mkdir(parents=True, exist_ok=True)
        self.tools: dict[str, CreatedTool] = {}
        self._load()

    def register(self, tool: CreatedTool):
        self.tools[tool.tool_id] = tool
        self._save()

    def create_from_insight(self, name: str, description: str,
                            script_content: str, language: str = "python",
                            capabilities: list[str] | None = None) -> CreatedTool:
        """从 Reflector 的 tool_request insight 创建工具"""
        tool_id = hashlib.sha256(
            f"{name}{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12]

        script_path = self._tools_dir / f"{tool_id}.py"
        script_path.write_text(script_content)
        script_path.chmod(0o755)

        tool = CreatedTool(
            tool_id=tool_id,
            name=name,
            description=description,
            script_path=str(script_path),
            language=language,
            capabilities=capabilities or [],
            created_by="reflector",
        )
        self.register(tool)
        return tool

    def execute(self, tool_id: str, *args) -> tuple[bool, str]:
        """执行一个已注册的工具"""
        tool = self.tools.get(tool_id)
        if not tool:
            return False, f"Tool {tool_id} not found"

        if not Path(tool.script_path).exists():
            return False, f"Script {tool.script_path} not found"

        try:
            result = subprocess.run(
                ["python3", tool.script_path, *args],
                capture_output=True, text=True, timeout=60,
            )
            tool.usage_count += 1
            if result.returncode == 0:
                self._save()
                return True, result.stdout
            else:
                tool.success_rate = (
                    tool.success_rate * (tool.usage_count - 1) + 0
                ) / tool.usage_count
                self._save()
                return False, result.stderr
        except subprocess.TimeoutExpired:
            tool.usage_count += 1
            self._save()
            return False, "Tool execution timed out"

    def find_by_capability(self, capability: str) -> list[CreatedTool]:
        return [t for t in self.tools.values() if capability in t.capabilities]

    @property
    def most_used(self) -> list[CreatedTool]:
        return sorted(self.tools.values(), key=lambda t: t.usage_count, reverse=True)[:10]

    @property
    def summary(self) -> dict:
        return {
            "total_tools": len(self.tools),
            "total_uses": sum(t.usage_count for t in self.tools.values()),
            "most_used": [t.name for t in self.most_used[:5]],
        }

    def _save(self):
        try:
            data = {
                tid: {
                    "tool_id": t.tool_id,
                    "name": t.name,
                    "description": t.description,
                    "script_path": t.script_path,
                    "language": t.language,
                    "capabilities": t.capabilities,
                    "usage_count": t.usage_count,
                    "success_rate": t.success_rate,
                    "created_at": t.created_at,
                    "created_by": t.created_by,
                }
                for tid, t in self.tools.items()
            }
            self._registry_path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _load(self):
        if self._registry_path.exists():
            try:
                data = json.loads(self._registry_path.read_text())
                for tid, d in data.items():
                    self.tools[tid] = CreatedTool(**d)
            except (json.JSONDecodeError, OSError):
                pass
