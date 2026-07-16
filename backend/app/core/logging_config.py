"""统一日志配置。

之前整个项目里没有任何地方调用 logging.basicConfig 或配置根 logger，
这意味着所有 logger.info(...) 调用（包括请求日志中间件）在默认配置下
会被 Python 根 logger 的默认 WARNING 级别直接丢弃，实际上从未输出过。
"""
import logging
import sys

from app.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # 避免重复添加 handler（例如测试中多次调用 create_app）
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        root_logger.addHandler(handler)

    # 第三方库默认降噪，避免连接池/驱动的调试日志刷屏
    for noisy_logger in ("neo4j", "httpx", "aio_pika", "pika"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
