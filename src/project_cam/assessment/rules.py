"""Config loading for athlete movement assessment rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("configs/exercises/football_academy_u10.yaml")


def load_rules(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if "exercises" not in data:
        raise ValueError(f"{config_path} is missing an 'exercises' section")
    return data


def exercise_rules(config: dict[str, Any], exercise: str) -> dict[str, Any]:
    try:
        rules = config["exercises"][exercise]
    except KeyError as exc:
        available = ", ".join(sorted(config.get("exercises", {}).keys()))
        raise ValueError(f"Unknown exercise '{exercise}'. Available exercises: {available}") from exc
    return rules or {}

