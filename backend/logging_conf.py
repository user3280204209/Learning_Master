"""统一日志：控制台 + 按天滚动文件。

日志不是 print：它有级别、有来源、能落盘，出问题时可追溯。
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler

from config import LOG_DIR

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"

# Windows 控制台默认使用 GBK，中文日志会花屏；统一成 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if getattr(root, "_learning_configured", False):
        return

    root.setLevel(level)
    formatter = logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = TimedRotatingFileHandler(
        LOG_DIR / "app.log",
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # 第三方库的日志太吵，压低级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    root._learning_configured = True  # type: ignore[attr-defined]
