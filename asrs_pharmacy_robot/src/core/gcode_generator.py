from __future__ import annotations

from src.core.machine_config import MachineConfig


class GCodeGenerator:
    def __init__(self, config: MachineConfig):
        self.config = config

    def generate_dispense_cycle(self, x_med: float, y_med: float) -> list[str]:
        self.config.validate_xy(x_med, y_med)
        return [
            "G21",
            "G90",
            "G94",
            f"G1 X{x_med:.3f} Y{y_med:.3f} F{self.config.feed_xy}",
            f"G1 Z{self.config.z_low:.3f} F{self.config.feed_z}",
            f"G1 Z{self.config.z_high:.3f} F{self.config.feed_z}",
            (
                f"G1 X{self.config.destination_x:.3f} "
                f"Y{self.config.destination_y:.3f} F{self.config.feed_xy}"
            ),
            f"G1 Z{self.config.z_low:.3f} F{self.config.feed_z}",
            f"G1 Z{self.config.z_high:.3f} F{self.config.feed_z}",
            f"G1 X{self.config.home_x:.3f} Y{self.config.home_y:.3f} F{self.config.feed_home}",
        ]

