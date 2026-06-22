"""AlphaX Evolution Runtime — 自主进化引擎

数字实体丢进去，环境自然选择，自己往更好的方向进化。
"""

from evolution.environment import Environment, TickResult, DeployResult, MarketContext, SimulatedEnvironment
from evolution.chamber import BreedingChamber
from evolution.genepool import GenePool
from evolution.engine import NexusEngine, DayStats
