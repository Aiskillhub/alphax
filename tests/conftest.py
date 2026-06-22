"""测试配置：隔离数据目录"""

import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """每次测试用独立的数据目录，避免互相污染"""
    from config import config
    monkeypatch.setattr(config, "data_dir", tmp_path)
    monkeypatch.setattr(config, "organisms_path", tmp_path / "organisms.json")
    monkeypatch.setattr(config, "gene_pool_path", tmp_path / "gene_pool.json")
    monkeypatch.setattr(config, "ledger_path", tmp_path / "ledger.jsonl")
    return tmp_path
