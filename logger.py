import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path(os.getenv("LOG_DIR", "/logs"))
LOG_FILE = _LOG_DIR / "igrecipe.log"

_FMT = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(module)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _setup() -> logging.Logger:
    logger = logging.getLogger("igrecipe")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(_FMT)
        logger.addHandler(fh)
    except OSError:
        pass  # log dir not writable (e.g. local dev without /logs mount)

    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(_FMT)
    logger.addHandler(sh)

    return logger


log = _setup()
