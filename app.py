import sys
from pathlib import Path

# Add asrs_pharmacy_robot to sys.path
BASE_DIR = Path(__file__).resolve().parent / "asrs_pharmacy_robot"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.ui.supervision_window import main


if __name__ == "__main__":
    raise SystemExit(main())
