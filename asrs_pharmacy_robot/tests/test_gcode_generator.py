from src.core.gcode_generator import GCodeGenerator
from src.core.machine_config import MachineConfig


def test_generate_dispense_cycle_matches_validated_sequence():
    config = MachineConfig(
        z_high=-2.0,
        z_low=2.0,
        destination_x=9.5,
        destination_y=-2.9,
        home_x=0.0,
        home_y=0.0,
        feed_xy=600,
        feed_z=200,
        feed_home=300,
    )

    assert GCodeGenerator(config).generate_dispense_cycle(2.0, -9.1) == [
        "G21",
        "G90",
        "G94",
        "G1 X2.000 Y-9.100 F600",
        "G1 Z2.000 F200",
        "G1 Z-2.000 F200",
        "G1 X9.500 Y-2.900 F600",
        "G1 Z2.000 F200",
        "G1 Z-2.000 F200",
        "G1 X0.000 Y0.000 F300",
    ]

