from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.utils.exceptions import ConfigError


@dataclass(frozen=True)
class MachineConfig:
    z_high: float
    z_low: float
    destination_x: float
    destination_y: float
    home_x: float
    home_y: float
    feed_xy: int
    feed_z: int
    feed_home: int
    baudrate: int = 115200
    require_homing_before_dispense: bool = True
    safe_min_x: float = -300.0
    safe_max_x: float = 300.0
    safe_min_y: float = -300.0
    safe_max_y: float = 300.0

    @classmethod
    def from_json(cls, path: str | Path) -> "MachineConfig":
        config_path = Path(path)
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConfigError(f"Machine config not found: {config_path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid machine config JSON: {exc}") from exc

        try:
            return cls(**data)
        except TypeError as exc:
            raise ConfigError(f"Machine config has missing or unknown fields: {exc}") from exc

    def validate_xy(self, x: float, y: float) -> None:
        if not (self.safe_min_x <= x <= self.safe_max_x):
            raise ConfigError(f"X coordinate {x} is outside safe range")
        if not (self.safe_min_y <= y <= self.safe_max_y):
            raise ConfigError(f"Y coordinate {y} is outside safe range")

