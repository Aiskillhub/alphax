"""Layer 4: 服务目录

Agent Economy 的基础设施——Agent 注册、能力广播、服务发现。

每个 Organism 可以注册为一个服务提供者：
  - 注册自己的能力标签（"export_pdf", "search_index", "ui_design" 等）
  - 设定服务价格
  - 被其他 Agent 发现和调用
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from config import config


@dataclass
class Capability:
    """一项能力"""
    name: str           # e.g. "chat_export_markdown"
    description: str
    input_schema: dict  # 输入格式
    output_schema: dict # 输出格式
    avg_quality: float = 0.5  # 历史平均质量
    avg_latency_ms: float = 1000


@dataclass
class AgentProfile:
    """一个 Agent 的服务档案"""
    agent_id: str       # organism_id
    name: str           # 可读名称
    capabilities: list[Capability] = field(default_factory=list)
    base_price: float = 3.99
    price_per_task: float = 0.99
    available: bool = True
    total_tasks_completed: int = 0
    total_earned: float = 0.0
    registered_at: float = field(default_factory=time.time)


@dataclass
class ServiceDirectory:
    """服务目录——Agent 发现与匹配"""

    profiles: dict[str, AgentProfile] = field(default_factory=dict)
    _path: Path = config.data_dir / "service_directory.json"

    def __post_init__(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                for p in data.get("profiles", []):
                    profile = AgentProfile(
                        agent_id=p["agent_id"],
                        name=p["name"],
                        capabilities=[Capability(**c) for c in p.get("capabilities", [])],
                        base_price=p.get("base_price", 3.99),
                        price_per_task=p.get("price_per_task", 0.99),
                        total_tasks_completed=p.get("total_tasks_completed", 0),
                        total_earned=p.get("total_earned", 0),
                    )
                    self.profiles[profile.agent_id] = profile
            except (json.JSONDecodeError, OSError):
                pass

    def register(self, organism_id: str, name: str,
                 capabilities: list[Capability] | None = None,
                 base_price: float = 3.99) -> AgentProfile:
        """注册一个 Agent 到服务目录"""
        profile = AgentProfile(
            agent_id=organism_id,
            name=name,
            capabilities=capabilities or [],
            base_price=base_price,
        )
        self.profiles[organism_id] = profile
        self._save()
        return profile

    def unregister(self, organism_id: str):
        """Agent 死亡时注销"""
        self.profiles.pop(organism_id, None)
        self._save()

    def add_capability(self, organism_id: str, capability: Capability):
        """Agent 学到新能力时更新"""
        if organism_id in self.profiles:
            self.profiles[organism_id].capabilities.append(capability)
            self._save()

    def find_by_capability(self, capability_name: str) -> list[AgentProfile]:
        """按能力搜索 Agent"""
        results = []
        for profile in self.profiles.values():
            if not profile.available:
                continue
            for cap in profile.capabilities:
                if capability_name.lower() in cap.name.lower():
                    results.append(profile)
                    break
        return sorted(results, key=lambda p: (
            max((c.avg_quality for c in p.capabilities
                 if capability_name.lower() in c.name.lower()), default=0),
        ), reverse=True)

    def find_by_keyword(self, keyword: str) -> list[AgentProfile]:
        """关键词搜索"""
        q = keyword.lower()
        results = []
        for profile in self.profiles.values():
            if not profile.available:
                continue
            if q in profile.name.lower():
                results.append(profile)
                continue
            for cap in profile.capabilities:
                if q in cap.name.lower() or q in cap.description.lower():
                    results.append(profile)
                    break
        return results

    def top_performers(self, n: int = 5) -> list[AgentProfile]:
        """按收入排名"""
        ranked = sorted(
            self.profiles.values(),
            key=lambda p: p.total_earned,
            reverse=True,
        )
        return ranked[:n]

    def summary(self) -> dict:
        active = sum(1 for p in self.profiles.values() if p.available)
        return {
            "total_agents": len(self.profiles),
            "active_agents": active,
            "total_capabilities": sum(
                len(p.capabilities) for p in self.profiles.values()
            ),
            "total_tasks_completed": sum(
                p.total_tasks_completed for p in self.profiles.values()
            ),
            "total_earned": sum(
                p.total_earned for p in self.profiles.values()
            ),
            "unique_capabilities": len({
                c.name for p in self.profiles.values()
                for c in p.capabilities
            }),
        }

    def _save(self):
        self._path.write_text(json.dumps({
            "profiles": [
                {
                    "agent_id": p.agent_id,
                    "name": p.name,
                    "capabilities": [
                        {k: v for k, v in c.__dict__.items()} for c in p.capabilities
                    ],
                    "base_price": p.base_price,
                    "price_per_task": p.price_per_task,
                    "available": p.available,
                    "total_tasks_completed": p.total_tasks_completed,
                    "total_earned": p.total_earned,
                }
                for p in self.profiles.values()
            ]
        }, indent=2))
