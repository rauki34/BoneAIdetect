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

# 目标模块 -> 待搬迁函数名
PLAN = {
    'backend/core/security.py': [
        'filter_sensitive_content', 'detect_prompt_injection', 'sanitize_ai_input',
    ],
    'backend/core/ratelimit.py': ['check_rate_limit', 'rate_limit'],
    'backend/core/auth.py': [
        'get_current_user', 'require_auth', 'require_admin', 'require_role',
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

    blocks = []
    for module, (fnames, _deps) in report.items():
        dotted = module.replace('backend/', '').replace('/', '.').removesuffix('.py')
        names = ', '.join(fnames)
        blocks.append(f'from {dotted} import {names}  # noqa: E402\n')

    lines[anchor + 1:anchor + 1] = blocks
    return ''.join(lines)


def main():
    lines = SRC.read_text(encoding='utf-8').splitlines(keepends=True)
    tree = ast.parse(''.join(lines))
    module_names = collect_module_names(tree)

    fn_nodes = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}

    drop_lines = set()
    report = {}

    for module, fnames in PLAN.items():
        chunks = []
        deps = set()
        for fname in fnames:
            node = fn_nodes.get(fname)
            if node is None:
                raise SystemExit(f'未找到函数 {fname}')
            start = leading_comment_start(lines, node.lineno)
            chunks.append(''.join(lines[start - 1:node.end_lineno]))
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
