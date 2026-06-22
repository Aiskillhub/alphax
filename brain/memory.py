"""AlphaX 大脑 — SuperBrain 知识图谱集成

双层存储架构：
  Local: JSONL 账本（快速读写，容错）
  SuperBrain: SQLite 知识图谱（语义检索、图谱遍历、跨层关联）

所有决策经验最终沉淀为 SuperBrain 中的结构化记忆。
基因池、市场洞察、元策略均由 SuperBrain 图谱承载。
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import config

# SuperBrain 集成——用 importlib 避免 sys.path 污染
_sb_path = os.environ.get("SUPERBRAIN_PATH",
                           str(Path(__file__).parent.parent.parent / "superbrain"))


def _sb_import(module_name: str):
    """安全导入 SuperBrain 模块，不污染 AlphaX 的 sys.modules"""
    try:
        path = os.path.join(_sb_path, f"{module_name}.py")
        spec = importlib.util.spec_from_file_location(
            f"superbrain_{module_name}", path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            _saved_config = sys.modules.get("config")
            spec.loader.exec_module(mod)
            if _saved_config is not None:
                sys.modules["config"] = _saved_config
            return mod
    except Exception:
        return None


def _sb_call(func_name: str, *args, **kwargs):
    """安全调用 SuperBrain store 中的函数"""
    store = _sb_import("store")
    if store is None:
        return None
    fn = getattr(store, func_name, None)
    if fn is None:
        return None
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


@dataclass
class MemorySystem:
    """统一记忆系统：本地 JSONL + SuperBrain 知识图谱"""

    ledger: list[dict] = field(default_factory=list)
    _sb_available: bool = False

    def __post_init__(self):
        self._load_ledger()
        self._sb_available = self._check_superbrain()

    # ── 投放记录（本地 + SuperBrain）──

    def record_deploy(self, organism_id: str, genome_id: str, product_name: str):
        entry = {
            "type": "deploy",
            "organism_id": organism_id,
            "genome_id": genome_id,
            "product_name": product_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._append(entry)
        self._sb_remember(
            f"投放产品: {product_name} (organism={organism_id}, genome={genome_id})",
            tags="alphax,deploy,product", confidence=0.9)

    def record_result(self, organism_id: str, genome_id: str, days_alive: int,
                      total_earned: float, total_burned: float, survived: bool,
                      avg_rating: float = 0.0):
        net = total_earned - total_burned
        entry = {
            "type": "result", "organism_id": organism_id, "genome_id": genome_id,
            "days_alive": days_alive, "total_earned": total_earned,
            "total_burned": total_burned, "net_profit": net,
            "survived": survived, "avg_rating": avg_rating,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._append(entry)

        status = "存活" if survived else "死亡"
        self._sb_remember(
            f"投放结果[{status}]: genome={genome_id} days={days_alive} "
            f"revenue=${total_earned:.2f} net=${net:.2f}",
            tags=f"alphax,result,{'survived' if survived else 'died'}",
            confidence=0.85)

    def record_insight(self, category: str, content: str, confidence: float = 0.5):
        entry = {
            "type": "insight", "category": category,
            "content": content, "confidence": confidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._append(entry)
        self._sb_remember(
            f"[{category}] {content}",
            tags=f"alphax,insight,{category}", confidence=confidence)

    # ── 基因组记忆 ──

    def remember_genome(self, genome_id: str, fitness: float, survival_rate: float,
                        product_name: str = ""):
        self._sb_remember(
            f"基因组 {genome_id}: fitness={fitness:.2f} survival={survival_rate:.0%} "
            f"product={product_name}",
            tags="alphax,genome,gene_pool",
            confidence=min(0.9, 0.5 + fitness))

    def remember_market_pattern(self, title: str, detail: str, confidence: float):
        self._sb_remember(
            f"市场模式: {title} — {detail}",
            tags="alphax,pattern,market", confidence=confidence)

    # ── 知识查询 ──

    def get_training_data(self, min_samples: int = 10) -> list[dict]:
        results = [e for e in self.ledger if e["type"] == "result"]
        if len(results) < min_samples:
            return []
        return results

    def get_successful_genomes(self) -> list[str]:
        return [e["genome_id"] for e in self.ledger
                if e["type"] == "result" and e["survived"]]

    def get_failed_genomes(self) -> list[str]:
        return [e["genome_id"] for e in self.ledger
                if e["type"] == "result" and not e["survived"]]

    def get_insights(self, category: str | None = None) -> list[dict]:
        insights = [e for e in self.ledger if e["type"] == "insight"]
        if category:
            insights = [i for i in insights if i["category"] == category]
        return insights

    def query_knowledge_graph(self, keywords: str, limit: int = 10) -> list[dict]:
        """跨层知识检索——从 SuperBrain 图谱查询"""
        rows = _sb_call("search_by_keywords", keywords, limit=limit)
        if rows is None:
            return []
        return [
            {"id": r["id"], "content": r["content"],
             "tags": r.get("tags", ""), "confidence": r.get("confidence", 0.5)}
            for r in rows
        ]

    def get_knowledge_stats(self) -> dict:
        """获取知识图谱统计"""
        stats = _sb_call("get_stats")
        if stats is None:
            return {"available": False}
        return stats

    # ── 内部 ──

    def _append(self, entry: dict):
        self.ledger.append(entry)
        with open(config.ledger_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _load_ledger(self):
        if config.ledger_path.exists():
            with open(config.ledger_path) as f:
                self.ledger = [json.loads(line) for line in f if line.strip()]

    def _check_superbrain(self) -> bool:
        result = _sb_call("check_connection")
        return result is True

    def _sb_remember(self, content: str, tags: str = "", confidence: float = 0.5):
        _sb_call("set_namespace", config.superbrain_namespace)
        _sb_call("add_memory",
                 content=content, tags=tags, confidence=confidence,
                 source="alphax", namespace=config.superbrain_namespace)
