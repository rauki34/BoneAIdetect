"""统一日志配置

替代散落的 print()，提供：
- 控制台输出（保持开发时可见）
- 文件输出（10MB 轮转，保留 5 份）
- 统一的格式：时间 [级别] 模块:行号 - 消息

用法：
    from utils.logger import logger
    logger.info("服务启动")
    logger.error("调用失败", exc_info=True)      # 自动带堆栈
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / 'logs'
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

MAX_BYTES = 10 * 1024 * 1024   # 10MB
BACKUP_COUNT = 5               # 保留 5 份历史


def get_logger(name: str = 'app', level: int = logging.INFO) -> logging.Logger:
    """获取（并初始化）一个 logger

    重复调用返回同一个实例，不会重复添加 handler。
    """
    logger = logging.getLogger(name)
    if logger.handlers:          # 已初始化过
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # --- 控制台 ---
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # --- 文件（轮转）---
    try:
        LOG_DIR.mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_DIR / f'{name}.log',
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding='utf-8',
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as e:
        # 日志目录不可写时降级为仅控制台，不影响主流程
        logger.warning('无法创建日志文件，仅输出到控制台: %s', e)

    logger.propagate = False     # 避免向 root logger 重复传播
    return logger


# 默认 logger（供模块直接 import 使用）
logger = get_logger('app')
