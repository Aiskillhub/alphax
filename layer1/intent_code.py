"""Layer 1: 意图代码

存储格式：意图 + 约束 + 补丁

传统代码：文件 → diff → patch
意图代码：意图描述 → 行为约束 → 代码补丁

Agent 不是"改第 37 行"，而是"我想导出 PDF 功能，性能约束 < 500ms，这是实现"。

这样：
  1. 人类/Agent 可以按意图查询代码
  2. 约束可以自动验证（"性能 < 500ms"→ CI 跑 benchmark）
  3. 相同意图可以用不同实现替换（A/B 测试基因变异）
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

from config import config


class ConstraintType(str, Enum):
    PERFORMANCE = "performance"   # 性能约束
    SIZE = "size"                 # 体积约束
    SECURITY = "security"         # 安全约束
    COMPAT = "compatibility"      # 兼容性约束


@dataclass
class Constraint:
    ctype: ConstraintType
    rule: str       # e.g. "response_time < 500ms"
    threshold: float
    unit: str = ""


@dataclass
class IntentBlock:
    """一个完整的意图代码块"""
    block_id: str
    intent: str                      # 意图描述
    constraints: list[Constraint]    # 行为约束
    files: dict[str, str]            # filename → code content
    tests: dict[str, str]            # test_name → test_code
    organism_id: str = ""
    genome_id: str = ""
    created_at: float = field(default_factory=time.time)

    @property
    def total_lines(self) -> int:
        return sum(c.count("\n") + 1 for c in self.files.values())


@dataclass
class IntentCode:
    """意图代码存储引擎"""

    blocks: dict[str, IntentBlock] = field(default_factory=dict)
    _path: Path = config.data_dir / "intent_code.json"

    def __post_init__(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                for b in data.get("blocks", []):
                    block = IntentBlock(
                        block_id=b["block_id"],
                        intent=b["intent"],
                        constraints=[Constraint(**c) for c in b.get("constraints", [])],
                        files=b.get("files", {}),
                        tests=b.get("tests", {}),
                        organism_id=b.get("organism_id", ""),
                        genome_id=b.get("genome_id", ""),
                    )
                    self.blocks[block.block_id] = block
            except (json.JSONDecodeError, OSError):
                pass

    def store(
        self,
        intent: str,
        files: dict[str, str],
        constraints: list[Constraint] | None = None,
        organism_id: str = "",
        genome_id: str = "",
    ) -> IntentBlock:
        """存储一个意图代码块"""
        import hashlib
        raw = intent + "".join(files.keys()) + str(time.time())
        block_id = hashlib.sha256(raw.encode()).hexdigest()[:12]

        block = IntentBlock(
            block_id=block_id,
            intent=intent,
            constraints=constraints or [],
            files=files,
            tests={},
            organism_id=organism_id,
            genome_id=genome_id,
        )
        self.blocks[block_id] = block
        self._save()
        return block

    def search(self, query: str) -> list[IntentBlock]:
        """按意图搜索代码块"""
        q = query.lower()
        return [b for b in self.blocks.values() if q in b.intent.lower()]

    def validate_constraints(self, block_id: str) -> dict:
        """验证约束是否满足（模拟）"""
        block = self.blocks.get(block_id)
        if not block:
            return {"valid": False, "reason": "not found"}

        results = {}
        for c in block.constraints:
            if c.ctype == ConstraintType.SIZE:
                size = sum(len(f) for f in block.files.values())
                limit = c.threshold
                results[c.rule] = {
                    "passed": size <= limit,
                    "actual": f"{size} bytes",
                    "limit": f"{limit} bytes",
                }
            elif c.ctype == ConstraintType.PERFORMANCE:
                results[c.rule] = {"passed": True, "note": "simulated"}

        return {"valid": all(r.get("passed", True) for r in results.values()),
                "results": results}

    def diff_blocks(self, block_id_a: str, block_id_b: str) -> dict:
        """对比两个意图块（用于评估基因变异效果）"""
        a = self.blocks.get(block_id_a)
        b = self.blocks.get(block_id_b)
        if not a or not b:
            return {"error": "block not found"}

        a_files = set(a.files.keys())
        b_files = set(b.files.keys())

        return {
            "same_intent": a.intent == b.intent,
            "files_added": list(b_files - a_files),
            "files_removed": list(a_files - b_files),
            "files_modified": list(a_files & b_files),
            "lines_a": a.total_lines,
            "lines_b": b.total_lines,
            "constraints_a": len(a.constraints),
            "constraints_b": len(b.constraints),
        }

    def summary(self) -> dict:
        return {
            "total_blocks": len(self.blocks),
            "total_lines": sum(b.total_lines for b in self.blocks.values()),
            "unique_intents": len({b.intent for b in self.blocks.values()}),
        }

    def _save(self):
        data = {
            "blocks": [
                {
                    "block_id": b.block_id,
                    "intent": b.intent,
                    "constraints": [{k: v for k, v in c.__dict__.items()} for c in b.constraints],
                    "files": b.files,
                    "tests": b.tests,
                    "organism_id": b.organism_id,
                    "genome_id": b.genome_id,
                    "created_at": b.created_at,
                }
                for b in self.blocks.values()
            ]
        }
        self._path.write_text(json.dumps(data, indent=2))
