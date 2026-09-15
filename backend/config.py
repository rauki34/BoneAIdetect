"""应用配置

配置优先级（从高到低）：
1. 环境变量（含 .env 文件加载的值）
2. 本文件中的默认值

通过 FLASK_ENV 环境变量切换配置类：
    FLASK_ENV=development（默认） / production
"""
import os
from pathlib import Path

# 项目路径
BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / 'instance'
LOG_DIR = BASE_DIR / 'logs'


def _env(key, default):
    """读取环境变量

    与 os.environ.get 的区别：空字符串视为未设置，回退到默认值。
    这样 .env 中写 `DATABASE_URL=` 或 `KEY=` 不会意外覆盖默认配置。
    """
    value = os.environ.get(key)
    return value if value not in (None, '') else default


class Config:
    """基础配置"""

    # ---------- 安全 ----------
    SECRET_KEY = _env('SECRET_KEY', 'dev-secret-key-change-in-production')

    # ---------- Session ----------
    PERMANENT_SESSION_LIFETIME = 3600        # 1 小时
    SESSION_COOKIE_SAMESITE = 'None'         # 允许跨域携带 cookie
    SESSION_COOKIE_SECURE = False            # 开发环境使用 HTTP

    # ---------- 数据库 ----------
    # 默认 SQLite；设置 DATABASE_URL 环境变量可切换到 PostgreSQL
    SQLALCHEMY_DATABASE_URI = _env(
        'DATABASE_URL',
        f'sqlite:///{INSTANCE_DIR / "bone_detection.db"}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ---------- JWT ----------
    JWT_SECRET_KEY = _env('JWT_SECRET_KEY', SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = int(_env('JWT_EXPIRES_SECONDS', 60 * 60 * 24 * 7))  # 7 天

    # ---------- CORS ----------
    CORS_ORIGINS = _env(
        'CORS_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173'
    ).split(',')

    # ---------- 外部服务 ----------
    AI_SERVICE_URL = _env('AI_SERVICE_URL', 'http://127.0.0.1:8000')

    # ---------- 限流 ----------
    RATE_LIMIT_AI = int(_env('RATE_LIMIT_AI', 10))            # AI 对话：次/分钟
    RATE_LIMIT_GENERAL = int(_env('RATE_LIMIT_GENERAL', 100))  # 通用：次/分钟


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
}

# 便捷访问：from config import config
config = config_map[os.environ.get('FLASK_ENV', 'development')]
