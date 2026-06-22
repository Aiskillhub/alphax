"""统一 fitness 计算

AGIStore 真实市场数据 → fitness score → 驱动进化决策。
"""

from __future__ import annotations


def compute_fitness(
    revenue: float = 0,
    downloads: int = 0,
    rating: float = 0,
    success_rate: float = 0,
    days_alive: int = 0,
) -> float:
    """从 AGIStore 数据计算 fitness (0-100)

    权重:
      收入 40% — 真金白银
      下载 20% — 装机量
      评分 25% — 用户满意度
      成功率 15% — Agent 执行质量
    """
    revenue_score = min(revenue / 50, 1.0) * 40
    download_score = min(downloads / 100, 1.0) * 20
    rating_score = (rating / 5.0) * 25
    success_score = (success_rate / 100.0) * 15

    return revenue_score + download_score + rating_score + success_score


def compute_fitness_from_stats(stats: dict, feedback: dict | None = None) -> float:
    """从 AGIStore stats + feedback API 返回计算 fitness"""
    revenue = float(stats.get("revenue", 0))
    downloads = int(stats.get("downloads", 0))
    rating = float(stats.get("rating", 0))

    success_rate = 0.0
    if feedback:
        success_rate = float(feedback.get("successRate", 0))

    return compute_fitness(
        revenue=revenue,
        downloads=downloads,
        rating=rating,
        success_rate=success_rate,
    )


def fitness_delta(current: float, previous: float) -> str:
    """返回 fitness 变化趋势"""
    if previous == 0:
        return "new"
    diff = current - previous
    if diff > 5:
        return "rising"
    elif diff < -5:
        return "declining"
    return "stable"
