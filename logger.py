import logging
import sys
from pathlib import Path

_LOG_FILE = Path(__file__).parent / "pawpal.log"
_FMT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    """Return a named logger that writes to both console (WARNING+) and pawpal.log (DEBUG+)."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # File handler — full detail
    fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))
    logger.addHandler(fh)

    # Console handler — warnings and above only
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))
    logger.addHandler(ch)

    return logger
