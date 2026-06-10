from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "[%(asctime)s] [%(levelname)-5s] [%(name)s] %(message)s  [%(filename)s:%(lineno)d]"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"
_configured = False


def setup_logging(level: int | None = None, log_dir: Path | None = None) -> None:
    global _configured
    if _configured:
        return

    if level is None:
        raw = os.environ.get("TASKPPS_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, raw, logging.INFO)

    root = logging.getLogger("taskpps")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    fmt = logging.Formatter(_FORMAT, _DATE_FMT)

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    if log_dir is None:
        try:
            from taskpps.config import get_data_dir

            log_dir = get_data_dir()
        except Exception:
            log_dir = Path.cwd() / ".taskpps"

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "server.log"

    fh = RotatingFileHandler(str(log_file), maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    _configured = True

    root.debug("Logging configured: level=%s file=%s", logging.getLevelName(level), log_file)
