import sys
from pathlib import Path

# Ensure project root is in Python sys.path
PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from src.ui.supervision_window import main


if __name__ == "__main__":
    raise SystemExit(main())
