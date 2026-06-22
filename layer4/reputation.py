"""Layer 4: 信誉系统

抵押信任 + 历史评分 + 衰减机制

信誉分影响：
  1. 竞标优先级（高信誉 Agent 更容易中标）
  2. 托管抵押要求（低信誉需要更高抵押）
  3. 服务目录排名

计算：
  信誉分 = 0.4 × 完成率 + 0.3 × 评分 + 0.2 × 抵押因子 + 0.1 × 活跃度
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from config import config


@dataclass
class Rating:
    """一次工作评分"""
    from_agent_id: str
    to_agent_id: str
    deal_id: str
    score: float          # 1-5
    comment: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class ReputationScore:
    """Agent 的信誉分"""
    agent_id: str
    overall: float = 3.0       # 综合分 1-5
    completion_rate: float = 1.0  # 任务完成率
    avg_rating: float = 3.0    # 平均评分
    staked_amount: float = 0.0 # 抵押金额
    total_ratings: int = 0
    total_deals: int = 0
    completed_deals: int = 0
    active_days: int = 0


@dataclass
class ReputationSystem:
    """信誉管理系统"""

    scores: dict[str, ReputationScore] = field(default_factory=dict)
    ratings: list[Rating] = field(default_factory=list)
    _path: Path = config.data_dir / "reputation.json"

    def __post_init__(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self.scores = {
                    s["agent_id"]: ReputationScore(**s)
                    for s in data.get("scores", [])
                }
                self.ratings = [Rating(**r) for r in data.get("ratings", [])]
            except (json.JSONDecodeError, OSError):
                pass

    def get_or_create(self, agent_id: str) -> ReputationScore:
        if agent_id not in self.scores:
            self.scores[agent_id] = ReputationScore(agent_id=agent_id)
        return self.scores[agent_id]

    def rate(self, from_agent: str, to_agent: str, deal_id: str,
             score: float, comment: str = "") -> Rating:
        """评价一个 Agent"""
        score = max(1.0, min(5.0, score))
        rating = Rating(
            from_agent_id=from_agent,
            to_agent_id=to_agent,
            deal_id=deal_id,
            score=score,
            comment=comment,
        )
        self.ratings.append(rating)

        # 更新被评分者的信誉
        rep = self.get_or_create(to_agent)
        rep.total_ratings += 1
        rep.avg_rating = (
            (rep.avg_rating * (rep.total_ratings - 1) + score)
            / rep.total_ratings
        )
        self._recalculate(to_agent)
        self._save()
        return rating

    def record_deal_complete(self, agent_id: str, success: bool):
        """记录一笔交易完成"""
        rep = self.get_or_create(agent_id)
        rep.total_deals += 1
        if success:
            rep.completed_deals += 1
        rep.completion_rate = (
            rep.completed_deals / max(rep.total_deals, 1)
        )
        self._recalculate(agent_id)
        self._save()

    def stake(self, agent_id: str, amount: float):
        """抵押资金（提高信誉）"""
        rep = self.get_or_create(agent_id)
        rep.staked_amount += amount
        self._recalculate(agent_id)
        self._save()

    def _recalculate(self, agent_id: str):
        """重新计算综合信誉分"""
        rep = self.scores.get(agent_id)
        if not rep:
            return

        # 抵押因子：抵押越多 → 越可信（饱和在 $50）
        stake_factor = min(rep.staked_amount / 50.0, 1.0)

        # 活跃度因子
        activity_factor = min(rep.total_deals / 20.0, 1.0)

        rep.overall = round(
            0.4 * rep.completion_rate * 5 +
            0.3 * rep.avg_rating +
            0.2 * stake_factor * 5 +
            0.1 * activity_factor * 5,
            2,
        )

    def rank(self, n: int = 10) -> list[tuple[str, float]]:
        """信誉排名"""
        ranked = sorted(
            self.scores.items(),
            key=lambda x: x[1].overall,
            reverse=True,
        )
        return [(aid, rep.overall) for aid, rep in ranked[:n]]

    def is_trusted(self, agent_id: str, threshold: float = 3.0) -> bool:
        """是否达到信任门槛"""
        rep = self.scores.get(agent_id)
        if not rep:
            return False
        return rep.overall >= threshold and rep.completion_rate >= 0.7

    def untrustworthy(self) -> list[str]:
        """低信誉 Agent 列表（需要关注）"""
        return [
            aid for aid, rep in self.scores.items()
            if rep.total_deals >= 3 and rep.overall < 2.0
        ]

    def stats(self) -> dict:
        if not self.scores:
            return {"total_agents": 0}

        avg = sum(s.overall for s in self.scores.values()) / len(self.scores)
        return {
            "total_agents": len(self.scores),
            "avg_reputation": round(avg, 2),
            "total_ratings": len(self.ratings),
            "total_staked": sum(s.staked_amount for s in self.scores.values()),
            "untrustworthy": len(self.untrustworthy()),
            "top_agent": self.rank(1)[0] if self.rank(1) else None,
        }

    def _save(self):
        self._path.write_text(json.dumps({
            "scores": [
                {k: v for k, v in s.__dict__.items()}
                for s in self.scores.values()
            ],
            "ratings": [
                {k: v for k, v in r.__dict__.items()} for r in self.ratings
            ],
        }, indent=2))
