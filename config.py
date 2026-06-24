"""AlphaX — 自主经济实体 配置"""

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).parent


def _load_dotenv(path: Path = None):
    """加载 .env 文件到 os.environ（纯 Python，零依赖）"""
    dotenv_path = path or ROOT / ".env"
    if not dotenv_path.exists():
        return
    with open(dotenv_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_dotenv()


@dataclass
class Config:
    # DeepSeek API (必须设置，否则无法运行)
    deepseek_api_key: str = field(default_factory=lambda: os.environ.get("DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = field(default_factory=lambda: os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    deepseek_model: str = field(default_factory=lambda: os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"))

    # FreeLLMAPI 聚合代理（可选，设置后优先走代理，省 token 费）
    freellmapi_url: str = field(default_factory=lambda: os.environ.get("FREELMAPI_URL", ""))
    freellmapi_key: str = field(default_factory=lambda: os.environ.get("FREELMAPI_KEY", ""))

    @property
    def has_llm(self) -> bool:
        return bool(self.deepseek_api_key)

    # 资金池
    initial_capital: float = 50.0        # 初始资金
    platform_fee_rate: float = 0.10      # 平台抽成 10%
    organism_energy_share: float = 0.70  # 个体留存 70%
    pool_share: float = 0.30            # 上缴资金池 30%

    # 个体生命周期
    hatch_energy: float = 5.0            # 孵化成本
    daily_burn_rate: float = 0.02        # 每日 API 消耗
    survival_threshold_days: int = 7     # 连续亏损多少天判定死亡
    breed_min_days: int = 30             # 最少存活天数才能繁殖
    breed_min_energy_positive_days: int = 21  # 净能量为正的天数

    # 种群
    max_population: int = 50             # 最大活跃个体数
    min_population_diversity: float = 0.3  # 种群多样性最低阈值

    # 探索 vs 剥削
    exploration_budget: float = 0.20     # 20% 预算用于随机探索

    # 基因
    mutation_rate: float = 0.10          # 每个位点 10% 突变概率
    mutation_strength: float = 0.25      # 突变幅度（价格 ±25%）

    # SuperBrain
    superbrain_namespace: str = "alphax"

    # 数据存储
    data_dir: Path = ROOT / "data"
    gene_pool_path: Path = ROOT / "data" / "gene_pool.json"
    organisms_path: Path = ROOT / "data" / "organisms.json"
    ledger_path: Path = ROOT / "data" / "ledger.jsonl"

    # Gumroad
    gumroad_access_token: str = field(default_factory=lambda: os.environ.get("GUMROAD_ACCESS_TOKEN", ""))

    # Chrome Web Store
    chrome_client_id: str = field(default_factory=lambda: os.environ.get("CHROME_CLIENT_ID", ""))
    chrome_client_secret: str = field(default_factory=lambda: os.environ.get("CHROME_CLIENT_SECRET", ""))
    chrome_refresh_token: str = field(default_factory=lambda: os.environ.get("CHROME_REFRESH_TOKEN", ""))

    # Stripe
    stripe_secret_key: str = field(default_factory=lambda: os.environ.get("STRIPE_SECRET_KEY", ""))
    stripe_publishable_key: str = field(default_factory=lambda: os.environ.get("STRIPE_PUBLISHABLE_KEY", ""))
    stripe_webhook_secret: str = field(default_factory=lambda: os.environ.get("STRIPE_WEBHOOK_SECRET", ""))

    # AGIStore (主市场)
    agistore_api_token: str = field(default_factory=lambda: os.environ.get("AGISTORE_API_TOKEN", ""))
    agistore_api_url: str = field(default_factory=lambda: os.environ.get("AGISTORE_API_URL", "http://localhost:3005"))

    def __post_init__(self):
        self.data_dir.mkdir(exist_ok=True)


config = Config()
