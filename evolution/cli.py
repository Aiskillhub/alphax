"""AlphaX Evolution Runtime — CLI 入口

Usage:
  python3 -m evolution.cli --days 30
  python3 -m evolution.cli --days 100 --env sim --seed 42
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evolution.engine import EvolutionEngine
from evolution.environment import SimulatedEnvironment
from config import config


def main():
    p = argparse.ArgumentParser(description="AlphaX Evolution Runtime")
    p.add_argument("--days", type=int, default=30, help="进化天数 (default: 30)")
    p.add_argument("--env", choices=["sim", "gumroad"], default="sim", help="环境类型")
    p.add_argument("--seed", type=int, default=42, help="随机种子")
    p.add_argument("--capital", type=float, default=50.0, help="初始资金")
    p.add_argument("--quiet", action="store_true", help="静默模式")
    args = p.parse_args()

    random.seed(args.seed)
    config.initial_capital = args.capital

    if args.env == "gumroad":
        print("GumroadEnvironment not yet implemented, falling back to sim.")
    env = SimulatedEnvironment(seed=args.seed)

    engine = EvolutionEngine(env=env)
    engine.run(days=args.days, verbose=not args.quiet)


if __name__ == "__main__":
    main()
