from __future__ import annotations

import argparse
from pathlib import Path

from src.core.asrs_controller import ASRSController
from src.core.machine_config import MachineConfig
from src.db.database import Database
from src.utils.logger import configure_logging


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = PROJECT_DIR / "config" / "machine_config.json"
DEFAULT_DB = PROJECT_DIR / "data" / "asrs.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SkyPharma ASRS backend CLI")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to machine_config.json")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to SQLite database")
    parser.add_argument("--port", help="GRBL serial port, for example COM5")
    parser.add_argument("--init-db", action="store_true", help="Create the database schema")
    parser.add_argument("--seed-test-medicine", action="store_true", help="Insert TestMed_A1 if missing")
    parser.add_argument("--list", action="store_true", help="List active medicines")
    parser.add_argument("--preview", type=int, metavar="ID", help="Print generated G-code for a medicine")
    parser.add_argument("--home", action="store_true", help="Connect and run GRBL homing")
    parser.add_argument("--dispense", type=int, metavar="ID", help="Connect and dispense a medicine")
    return parser


def main() -> int:
    configure_logging(PROJECT_DIR / "logs")
    args = build_parser().parse_args()
    config = MachineConfig.from_json(args.config)
    database = Database(args.db)

    if args.init_db:
        database.initialize()
        print(f"Database initialized: {args.db}")

    if args.seed_test_medicine:
        medicine_id = database.seed_test_medicine()
        print(f"Test medicine ready with id={medicine_id}")

    if args.list:
        for medicine in database.search_medicines():
            print(
                f"{medicine.id}: {medicine.name} "
                f"({medicine.x:.3f}, {medicine.y:.3f}) "
                f"stock={medicine.stock} location={medicine.location_label or '-'}"
            )

    controller = ASRSController(config, database)

    if args.preview is not None:
        print("\n".join(controller.preview_dispense(args.preview)))

    if args.home or args.dispense is not None:
        if not args.port:
            raise SystemExit("--port is required for --home and --dispense")
        controller.connect_machine(args.port)
        try:
            if args.home:
                controller.home()
                print("Homing completed")
            if args.dispense is not None:
                if config.require_homing_before_dispense and not controller.is_homed:
                    controller.home()
                    print("Homing completed")
                program = controller.distribute_medicine(args.dispense)
                print("Dispense completed")
                print("\n".join(program))
        finally:
            controller.disconnect_machine()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

