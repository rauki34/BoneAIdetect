"""一次性工具：把 app.py 中的函数按名搬迁到其他模块

用法：在脚本底部 PLAN 中声明 {目标模块: [函数名, ...]}，先试运行再 --apply。

行为：
1. 用 AST 取每个函数的精确源码区间（含装饰器）
2. 连同其上方紧邻的注释块一并搬迁（注释通常描述该函数）
3. 写入目标模块（保留原缩进与空行）
4. 从 app.py 删除对应行
5. 报告每个搬迁函数引用了哪些**模块级名字**，便于在目标模块补齐 import
"""
import ast
import sys
from pathlib import Path

SRC = Path('backend/app.py')
DRY_RUN = '--apply' not in sys.argv

# 模块级常量搬迁：{目标模块: [常量名, ...]}
CONSTANTS = {
    'backend/services/ai_service.py': ['AI_SYSTEM_PROMPT'],
}

# 函数体内 app.app_context() 需改写为 current_app.app_context() 的模块
NEEDS_CURRENT_APP = {'backend/services/ai_service.py'}

# 蓝图模块 -> 蓝图名（这些模块会把 @app.route 改写为 @bp.route）
BLUEPRINTS = {
    'backend/api/analysis.py': 'analysis',
    'backend/api/ai.py': 'ai',
    'backend/api/message.py': 'message',
}

# 蓝图模块中「路由函数名 -> 蓝图名」的映射在 PLAN 里由 BLUEPRINTS 推导
# 目标模块 -> 待搬迁函数名
PLAN = {
    'backend/api/ai.py': [
        'ai_assistant_chat_stream', 'ai_assistant_chat',
        'ai_assistant_history', 'ai_assistant_sessions',
    ],
    'backend/api/message.py': [
        'send_message', 'get_conversation', 'get_message_contacts',
        'mark_messages_read', 'get_announcements',
        'mark_announcement_read', 'get_unread_announcement_count',
    ],
}

MODULE_HEADERS = {
    'backend/core/validators.py': '''"""输入校验工具

从 app.py 抽出，供各蓝图与注册/登录流程共用。
"""
import re
from datetime import datetime

''',
    'backend/core/helpers.py': '''"""通用辅助函数

从 app.py 抽出，供各蓝图共用。
"""
from flask import request

from database import db, OperationLog
from utils.logger import logger

''',
    'backend/core/captcha.py': '''"""图形验证码校验

从 app.py 抽出。验证码存于 core.state.captcha_store（进程内，5 分钟过期）。
"""
import time

from core.state import captcha_store

''',
    'backend/services/ai_service.py': '''"""AI 服务层

从 app.py 抽出：AI 配置读取、统一 LLM 客户端构造、医疗建议生成、
助手对话调用与降级回复。被 api/ai.py 与 api/detection.py 共用。
"""
import json
import threading
from datetime import datetime

from flask import current_app

from database import db, AIConversation, DetectionHistory, SystemSettings
from services.llm_client import LLMClient, LLMError
from utils.logger import logger

''',
    'backend/api/ai.py': '''"""AI 助手对话接口

路由保留完整路径（不使用 url_prefix），确保 URL 与拆分前一致。
"""
import json

from flask import Blueprint, Response, current_app, jsonify, request

from core.auth import get_current_user, require_auth, require_role
from database import db, AIConversation
from services.ai_service import (
    _build_assistant_messages, call_ai_assistant_api, get_llm_client,
)
from services.llm_client import LLMError
from utils.logger import logger

bp = Blueprint('ai', __name__)

''',
    'backend/api/message.py': '''"""医患消息与系统公告接口

路由保留完整路径（不使用 url_prefix），确保 URL 与拆分前一致。
"""
from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from core.auth import get_current_user, require_auth, require_role
from core.helpers import log_operation
from database import (
    Announcement, AnnouncementRead, DoctorPatientRelation,
    DoctorProfile, Message, PatientProfile, User, db,
)
from utils.logger import logger

bp = Blueprint('message', __name__)

''',
    'backend/core/security.py': '''"""AI 内容安全

从 app.py 抽出：敏感词过滤、提示词注入检测、输入净化。

注意：当前为黑名单式防护，可被同义改写 / 编码绕过。
"""
import re

# 敏感词列表
SENSITIVE_WORDS = [
    '密码', 'password', '身份证', 'id card', 'credit card', '信用卡',
    '银行卡', 'bank account', '社保', 'social security',
    'api_key', 'secret', 'token', 'private key'
]

# 提示词注入检测模式
PROMPT_INJECTION_PATTERNS = [
    r'ignore\\s+(previous|above|all)\\s+instructions?',
    r'forget\\s+(everything|all|previous)',
    r'you\\s+are\\s+now',
    r'new\\s+instructions?',
    r'system\\s*:\\s*',
    r'<\\s*script\\s*>',
    r'javascript\\s*:',
    r'eval\\s*\\(',
    r'exec\\s*\\(',
]


''',
    'backend/core/ratelimit.py': '''"""请求限流

从 app.py 抽出。基于进程内滑动窗口，多 worker 部署时不共享，
应迁至 Redis（见 BASELINE 待办）。
"""
from datetime import datetime
from functools import wraps

from flask import jsonify

from core.auth import get_current_user
from core.helpers import log_operation
from core.state import RATE_LIMIT_CONFIG, rate_limit_lock, rate_limit_storage

''',
    'backend/core/auth.py': '''"""认证与权限装饰器

从 app.py 抽出。当前为 JWT + X-Username 双模式过渡期实现，
全量切换后移除兜底分支。
"""
from datetime import datetime
from functools import wraps

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from core.helpers import log_operation
from database import User
from utils.logger import logger

''',
    'backend/api/analysis.py': '''"""统计分析接口

路由保留完整路径（不使用 url_prefix），确保 URL 与拆分前一致。
"""
import json

from flask import Blueprint, jsonify, request

from core.auth import get_current_user, require_admin, require_auth, require_role
from database import db, DetectionHistory, Examination, User

bp = Blueprint('analysis', __name__)

''',
}


def leading_comment_start(lines, lineno):
    """向上吞掉紧邻的注释块（中间允许空行）"""
    start = lineno
    i = lineno - 2                      # 转 0-based，指向上一行
    while i >= 0:
        stripped = lines[i].strip()
        if stripped == '':
            # 空行：仅当再上一行是注释时才继续
            if i - 1 >= 0 and lines[i - 1].strip().startswith('#'):
                i -= 1
                continue
            break
        if stripped.startswith('#'):
            start = i + 1
            i -= 1
            continue
        break
    return start


def collect_module_names(tree):
    """收集模块级名字：变量赋值、函数、类、import"""
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.FunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                names.add((a.asname or a.name).split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
    return names


def used_globals(fn_node, module_names):
    """函数体内引用到的模块级名字（排除局部变量与参数）"""
    local = set()
    for n in ast.walk(fn_node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            local.add(n.id)
        elif isinstance(n, ast.arg):
            local.add(n.arg)
    used = set()
    for n in ast.walk(fn_node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            if n.id in module_names and n.id not in local:
                used.add(n.id)
    return used


def insert_imports(src, report):
    """在被搬走的函数原位所在的导入区补上 import

    插入点：文件中最后一个 `from core.` 导入块之后；若没有则退回
    最后一个顶层 import 之后。
    """
    lines = src.splitlines(keepends=True)
    anchor = None
    for i, line in enumerate(lines):
        if line.startswith('from core.') or line.startswith('from services.'):
            anchor = i
            # 吞掉多行导入的后续行
            while anchor + 1 < len(lines) and not lines[anchor].strip().endswith(')'):
                if lines[anchor].rstrip().endswith(')'):
                    break
                anchor += 1
                if lines[anchor].rstrip().endswith(')'):
                    break
    if anchor is None:
        raise SystemExit('未找到导入插入锚点，请手动添加 import')

    blocks, regs = [], []
    for module, (fnames, _deps) in report.items():
        dotted = module.replace('backend/', '').replace('/', '.').removesuffix('.py')
        if module in BLUEPRINTS:
            # 蓝图：导入 bp 对象并注册，而不是导入被搬走的函数
            bp_name = BLUEPRINTS[module]
            blocks.append(f'from {dotted} import bp as {bp_name}_bp  # noqa: E402\n')
            regs.append(f'app.register_blueprint({bp_name}_bp)\n')
        else:
            names = ', '.join(fnames)
            blocks.append(f'from {dotted} import {names}  # noqa: E402\n')

    lines[anchor + 1:anchor + 1] = blocks
    src = ''.join(lines)

    if regs:
        src = insert_registrations(src, regs)
    return src


def insert_registrations(src, regs):
    """把 app.register_blueprint(...) 追加到蓝图注册区末尾"""
    marker = 'app.register_blueprint('
    lines = src.splitlines(keepends=True)
    last = None
    for i, line in enumerate(lines):
        if line.startswith(marker):
            last = i
            # 跳过跨行调用
            while not lines[last].rstrip().endswith(')'):
                last += 1
    if last is None:
        raise SystemExit('未找到蓝图注册锚点，请手动注册')
    lines[last + 1:last + 1] = regs
    return ''.join(lines)


def to_blueprint(chunk, bp_name, url_prefix=None):
    """把函数源码中的 @app.route 改写为 @bp.route

    刻意不使用 url_prefix：路由保留完整路径（如 /api/admin/dashboard），
    保证 URL 与拆分前完全一致，也免去改写路径的风险。
    """
    chunk = chunk.replace('@app.route(', '@bp.route(')
    # 唯一的 app.app_context() 用法（AI 流式接口）改为 current_app
    chunk = chunk.replace('with app.app_context():', 'with current_app.app_context():')
    return chunk


def main():
    lines = SRC.read_text(encoding='utf-8').splitlines(keepends=True)
    tree = ast.parse(''.join(lines))
    module_names = collect_module_names(tree)

    fn_nodes = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    const_nodes = {}
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    const_nodes[t.id] = n

    drop_lines = set()
    report = {}

    for module, fnames in PLAN.items():
        chunks = []
        deps = set()

        # 先搬常量
        for cname in CONSTANTS.get(module, []):
            node = const_nodes.get(cname)
            if node is None:
                raise SystemExit(f'未找到常量 {cname}')
            start = leading_comment_start(lines, node.lineno)
            chunks.append(''.join(lines[start - 1:node.end_lineno]))
            for ln in range(start, node.end_lineno + 1):
                drop_lines.add(ln)

        for fname in fnames:
            node = fn_nodes.get(fname)
            if node is None:
                raise SystemExit(f'未找到函数 {fname}')
            # node.lineno 指向 def 行，不含装饰器；必须从首个装饰器算起，
            # 否则 @app.route / @require_auth 会被丢掉
            first_line = (node.decorator_list[0].lineno
                          if node.decorator_list else node.lineno)
            start = leading_comment_start(lines, first_line)
            chunk = ''.join(lines[start - 1:node.end_lineno])
            if module in BLUEPRINTS:
                chunk = to_blueprint(chunk, BLUEPRINTS[module])
            if module in NEEDS_CURRENT_APP:
                chunk = chunk.replace('with app.app_context():',
                                      'with current_app.app_context():')
            chunks.append(chunk)
            for ln in range(start, node.end_lineno + 1):
                drop_lines.add(ln)
            deps |= used_globals(node, module_names)
        report[module] = (fnames, sorted(deps))

        if not DRY_RUN:
            p = Path(module)
            p.parent.mkdir(parents=True, exist_ok=True)
            body = '\n\n'.join(c.rstrip('\n') for c in chunks)
            header = MODULE_HEADERS.get(module, '')
            p.write_text(header + body + '\n', encoding='utf-8')

    if not DRY_RUN:
        new_lines = [l for i, l in enumerate(lines, 1) if i not in drop_lines]
        src = ''.join(new_lines)
        src = insert_imports(src, report)
        SRC.write_text(src, encoding='utf-8')

    print('=' * 70)
    for module, (fnames, deps) in report.items():
        print(f'{module}')
        for f in fnames:
            print(f'    - {f}')
        print(f'    依赖的模块级名字: {deps}')
        print()
    print('=' * 70)
    print(f'{"试运行，未写入" if DRY_RUN else "已写入"}')
    print(f'app.py: {len(lines)} 行 -> {len(lines) - len(drop_lines)} 行')


if __name__ == '__main__':
    main()
