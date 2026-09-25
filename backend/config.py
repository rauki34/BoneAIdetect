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

    # 连接池健壮性。
    #
    # pool_pre_ping：取用池中连接前先发一次极轻量的探活，连接已死就丢弃重连。
    #   不加它的后果是**服务端重启后第一批请求会失败** —— 池里握的全是死连接，
    #   要等它们被逐个淘汰才恢复。本机的 PostgreSQL 今天崩过两次（0xC0000142，
    #   事件日志提示可能是杀毒软件注入 DLL 所致，与代码无关），每次都会踩到。
    #   代价是每个请求多一次往返，同机部署可以忽略。
    # pool_recycle：连接最长存活 30 分钟就回收，避免踩到服务端或中间设备的
    #   空闲超时（故障表现同样是"用着用着突然报错"）。
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 1800,
    }

    # ---------- JWT ----------
    JWT_SECRET_KEY = _env('JWT_SECRET_KEY', SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = int(_env('JWT_EXPIRES_SECONDS', 60 * 60 * 24 * 7))  # 7 天

    # ---------- CORS ----------
    CORS_ORIGINS = _env(
        'CORS_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173'
    ).split(',')

    # ---------- 缓存 ----------
    # 限流计数、验证码等；不可用时各模块自动降级为进程内存储
    REDIS_URL = _env('REDIS_URL', 'redis://127.0.0.1:6379/0')

    # ---------- 外部服务 ----------
    AI_SERVICE_URL = _env('AI_SERVICE_URL', 'http://127.0.0.1:8000')

    # ---------- RAG 知识库 ----------
    # 总开关：显存吃紧或演示时需要把 GPU 让给 YOLO 时置 false，
    # 对话会退回"无参考资料"的普通回答，其余功能不受影响
    RAG_ENABLED = _env('RAG_ENABLED', 'true').lower() == 'true'
    RAG_EMBED_MODEL = _env('RAG_EMBED_MODEL', 'BAAI/bge-m3')
    RAG_RERANK_MODEL = _env('RAG_RERANK_MODEL', 'BAAI/bge-reranker-v2-m3')
    RAG_DEVICE = _env('RAG_DEVICE', 'auto')                  # auto | cuda | cpu
    RAG_FP16 = _env('RAG_FP16', 'true').lower() == 'true'
    # 6GB 显存与 YOLO 共存时的安全值；YOLO 不占显存时可加大（--batch）
    RAG_EMBED_BATCH = int(_env('RAG_EMBED_BATCH', 8))
    RAG_RERANK_BATCH = int(_env('RAG_RERANK_BATCH', 8))
    RAG_TOP_K = int(_env('RAG_TOP_K', 5))
    RAG_RECALL_K = int(_env('RAG_RECALL_K', 20))
    RAG_RRF_K = int(_env('RAG_RRF_K', 60))
    # 患者本人病历的保障槽位数（避免被共享语料挤掉）
    RAG_PERSONAL_SLOTS = int(_env('RAG_PERSONAL_SLOTS', 2))
    RAG_MIN_SCORE = float(_env('RAG_MIN_SCORE', 0.0))
    # 启动时预热模型。默认关闭，避免拖慢启动；首次检索会慢 10-30 秒
    RAG_WARMUP = _env('RAG_WARMUP', 'false').lower() == 'true'
    RAG_CACHE_TTL = int(_env('RAG_CACHE_TTL', 600))
    # 上传体积上限。入库搬到 Celery 后（阶段 8）这一项仍然必要：
    # 它限制的是 HTTP 请求体大小，与入库同步还是异步无关
    RAG_MAX_UPLOAD_MB = int(_env('RAG_MAX_UPLOAD_MB', 50))

    # ---------- Celery（阶段 8）----------
    # worker 与后端是两个进程，各自独立读环境变量
    CELERY_BROKER_URL = _env('CELERY_BROKER_URL', 'redis://127.0.0.1:6379/1')
    CELERY_RESULT_BACKEND = _env('CELERY_RESULT_BACKEND', 'redis://127.0.0.1:6379/2')

    # ---------- 限流 ----------
    RATE_LIMIT_AI = int(_env('RATE_LIMIT_AI', 10))            # AI 对话：次/分钟
    RATE_LIMIT_GENERAL = int(_env('RATE_LIMIT_GENERAL', 100))  # 通用：次/分钟

    # ---------- 额度（阶段 9）----------
    # 分钟级限流只约束"多快"，约束不了"总量"：一次 Agent 请求最坏触发 5 次
    # LLM 调用，按 5 次/分钟放行等于一小时能烧 25 次推演。所以要另一个尺度。
    # 语义与实现见 core/quota.py。
    QUOTA_ENABLED = _env('QUOTA_ENABLED', 'true').lower() == 'true'
    # 单个会话的对话轮数上限（新建会话即重置）
    QUOTA_SESSION_MAX = int(_env('QUOTA_SESSION_MAX', 30))
    # 单用户每日对话次数上限；日期边界用**本地日期**（不是 UTC，见 quota.py）
    QUOTA_DAILY_PER_USER = int(_env('QUOTA_DAILY_PER_USER', 100))
    QUOTA_SESSION_TTL = int(_env('QUOTA_SESSION_TTL', 604800))   # 会话计数保留 7 天
    # 豁免额度的角色（与 RATE_LIMIT_BYPASS_ROLES 同义；压测时可临时用 admin 账号）
    QUOTA_BYPASS_ROLES = _env('QUOTA_BYPASS_ROLES', 'admin').split(',')

    # 是否信任反向代理传来的 X-Forwarded-For。
    # 直连部署时必须保持 False —— 该头可被客户端伪造，
    # 信任它会让攻击者通过伪造 IP 绕过限流。
    TRUST_PROXY = _env('TRUST_PROXY', 'false').lower() == 'true'

    # 不限流的角色（急诊场景下不应因限流阻断医护使用）
    RATE_LIMIT_BYPASS_ROLES = _env('RATE_LIMIT_BYPASS_ROLES', 'admin').split(',')


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
