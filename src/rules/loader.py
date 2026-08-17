"""Generic cached YAML loader for data/seed/*.yaml and data/rules/*.yaml."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SEED_DIR = REPO_ROOT / "data" / "seed"
RULES_DIR = REPO_ROOT / "data" / "rules"
GOLDEN_DIR = REPO_ROOT / "data" / "golden"


@lru_cache
def load_seed(filename: str) -> dict:
    with (SEED_DIR / filename).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache
def load_rules(filename: str) -> dict:
    with (RULES_DIR / filename).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
