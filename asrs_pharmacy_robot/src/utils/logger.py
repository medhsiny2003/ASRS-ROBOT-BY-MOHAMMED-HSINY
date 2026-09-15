import logging
from pathlib import Path


def configure_logging(log_dir: str | Path = "logs") -> None:
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(path / "asrs.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

