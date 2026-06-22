"""Layer 1: 语义 Git

不是传统的 diff-based version control。
而是 intent-based：每个 commit 记录的是"我为什么改"而不是"我改了什么"。

Agent 提交代码时：
  intent: "实现一键导出 ChatGPT 对话为 PDF"
  → SemanticGit 生成 commit message
  → 关联到 SuperBrain 知识图谱的语义节点
  → 后续可以按意图查询代码变更
"""

from __future__ import annotations

import json
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum

from config import config


class ChangeType(str, Enum):
    FEATURE = "feature"
    FIX = "fix"
    REFACTOR = "refactor"
    OPTIMIZE = "optimize"
    TEST = "test"


@dataclass
class SemanticCommit:
    commit_id: str
    intent: str               # "为什么改"——人类/Agent 可读的意图描述
    change_type: ChangeType
    files_changed: list[str]  # 改了哪些文件
    agent_id: str             # 哪个 Agent 提交的
    organism_id: str          # 属于哪个 Organism
    genome_id: str            # 用了什么基因
    before_snapshot: str = "" # 改动前的语义摘要
    after_snapshot: str = ""  # 改动后的语义摘要
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    parent_commit: str = ""   # 上一个 commit ID
    metadata: dict = field(default_factory=dict)


@dataclass
class SemanticGit:
    """意图驱动的版本控制"""

    commits: list[SemanticCommit] = field(default_factory=list)
    _path: Path = config.data_dir / "semantic_git.json"

    def __post_init__(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self.commits = [SemanticCommit(**c) for c in data.get("commits", [])]
            except (json.JSONDecodeError, OSError):
                pass

    def commit(
        self,
        intent: str,
        change_type: ChangeType,
        files: list[str],
        agent_id: str,
        organism_id: str,
        genome_id: str,
        before: str = "",
        after: str = "",
    ) -> SemanticCommit:
        """创建一个语义 commit"""
        last_id = self.commits[-1].commit_id if self.commits else ""

        raw = f"{intent}{change_type}{''.join(files)}{agent_id}{time.time()}"
        commit_id = hashlib.sha256(raw.encode()).hexdigest()[:12]

        commit = SemanticCommit(
            commit_id=commit_id,
            intent=intent,
            change_type=change_type,
            files_changed=files,
            agent_id=agent_id,
            organism_id=organism_id,
            genome_id=genome_id,
            before_snapshot=before,
            after_snapshot=after,
            parent_commit=last_id,
        )
        self.commits.append(commit)
        self._save()
        return commit

    def search_by_intent(self, query: str) -> list[SemanticCommit]:
        """按意图搜索 commit（简单关键词匹配）"""
        q = query.lower()
        return [c for c in self.commits if q in c.intent.lower()]

    def get_history(self, organism_id: str) -> list[SemanticCommit]:
        """查看某个 Organism 的所有变更历史"""
        return [c for c in self.commits if c.organism_id == organism_id]

    def get_genome_performance(self, genome_id: str) -> dict:
        """分析某个基因组产生的代码质量"""
        related = [c for c in self.commits if c.genome_id == genome_id]
        if not related:
            return {"commits": 0, "bugs_fixed": 0, "features": 0}

        return {
            "commits": len(related),
            "bugs_fixed": sum(1 for c in related if c.change_type == ChangeType.FIX),
            "features": sum(1 for c in related if c.change_type == ChangeType.FEATURE),
            "first_commit": related[0].timestamp,
            "last_commit": related[-1].timestamp,
        }

    def summary(self) -> dict:
        return {
            "total_commits": len(self.commits),
            "unique_organisms": len({c.organism_id for c in self.commits}),
            "unique_genomes": len({c.genome_id for c in self.commits}),
            "recent_intents": [c.intent[:60] for c in self.commits[-5:]],
        }

    def _save(self):
        self._path.write_text(json.dumps({
            "commits": [
                {k: v for k, v in c.__dict__.items()} for c in self.commits
            ]
        }, indent=2))
