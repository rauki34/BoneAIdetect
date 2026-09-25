"""依赖声明对账

`backend/**.py` 里 import 的第三方顶层模块，必须在 `backend/requirements.txt`
里声明。**纯 AST 解析、不导入任何模块** —— 这正是它能待在 CI 里的原因：CI 装
的是轻量依赖（requirements-ci.txt，不装 torch），torch / torchvision /
ultralytics 这些重依赖压根装不进去，于是"代码 import 了、requirements 没写"
一直是 CI 的盲区。静态扫描不需要装包，正好把这条缝补上。

立这条守卫的直接原因：`services/rag/loader.py` 的 `load_docx()` 里有
`from docx import Document`（**惰性导入**，在函数体内），而 python-docx 在
任何一份 requirements 里都没写。本机 venv 是手工装的（pip show 的
Required-by 为空，不是谁的传递依赖），所以 pdf / md / txt 三条入库路径全部
正常、只有真上传 .docx 时才 ImportError —— 而 `verify_knowledge_api.py`
恰好只测了 pdf 与 md，这条分支连端到端验收都盖不到。

**没见过的 import 名一律判失败，不猜包名**：`cv2` → opencv-python 这类映射
写死在 IMPORT_TO_PACKAGE 里，遇到不认识的名字要人来判断它到底是本地模块还是
漏声明。猜错的方向是"把漏声明当成本地模块静默放过"，那比报错贵得多。
"""
import ast
import pathlib
import re
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[2]      # tests/unit/ → backend/
REQUIREMENTS = BACKEND / 'requirements.txt'

# import 名 → PyPI 发行名。只有两边名字对不上的才需要登记，名字一致的
# （flask / numpy / celery / pytest …）靠下面的归一化自己对上。
IMPORT_TO_PACKAGE = {
    'cv2': 'opencv-python',
    'PIL': 'Pillow',
    'docx': 'python-docx',
    'dotenv': 'python-dotenv',
    'flask_cors': 'Flask-CORS',
    'flask_jwt_extended': 'Flask-JWT-Extended',
    'flask_migrate': 'Flask-Migrate',
    'flask_sock': 'flask-sock',
    'flask_sqlalchemy': 'Flask-SQLAlchemy',
    'rank_bm25': 'rank-bm25',
    'sentence_transformers': 'sentence-transformers',
    'sklearn': 'scikit-learn',
    'yaml': 'PyYAML',
}


def _normalize(name):
    """PEP 503：发行名大小写不敏感，`-` / `_` / `.` 三者等价"""
    return re.sub(r'[-_.]+', '-', name).lower()


def _declared_packages():
    """requirements.txt 声明了哪些发行名（已归一化）"""
    declared = set()
    for line in REQUIREMENTS.read_text(encoding='utf-8').splitlines():
        line = line.split('#')[0].strip()
        match = re.match(r'^([A-Za-z0-9][A-Za-z0-9._-]*)', line)
        if match:
            declared.add(_normalize(match.group(1)))
    return declared


def _local_modules():
    """backend/ 顶层能解析到的本地模块名

    只取顶层：本仓所有代码都靠 `sys.path.insert(0, <backend>)` 定位导入，
    `from utils.logger import ...` 对应 backend/utils/，不存在更深的裸导入
    （包内互相引用走的是相对导入，已在扫描时跳过）。

    **不按 `__init__.py` 筛**：api / models / migrations 三个目录都没有
    `__init__.py`，却照样被 `from models.patient import ...` 这样导入
    —— Python 3.3 起它们是命名空间包，照样能用。

    但**目录里至少要有一个 .py 才算**（见 `_has_python`）：instance / logs /
    outputs / runs / uploads 这些运行期产物目录都被 gitignore，本机存在而 CI
    的 checkout 里没有。若把它们也算成本地模块，本机与 CI 就会拿两份不同的
    本地模块集去对账 —— 而本测试**没有 `__init__.py` 可依赖**，只能靠这条
    规则让两边尽量同集。残留差异：`logs/` 下真有一份未跟踪的探针脚本，所以
    本机仍比 CI 多认一个 `logs`。今天的目录名没有一个与第三方 import 重名，
    所以两边结论一致（已在干净树里逐字比对过）；将来若出现重名，这条会先红。
    """
    return {
        entry.stem if entry.is_file() and entry.suffix == '.py' else entry.name
        for entry in BACKEND.iterdir()
        if entry.name != '__pycache__'
        and (entry.is_file() and entry.suffix == '.py'
             or entry.is_dir() and _has_python(entry))
    }


def _has_python(directory):
    return next(directory.rglob('*.py'), None) is not None


def _third_party_imports():
    """扫出第三方顶层 import 名 → 它出现在哪些文件（相对路径，供报错定位）"""
    local = _local_modules()
    found = {}
    for path in sorted(BACKEND.rglob('*.py')):
        if '__pycache__' in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                names = [node.module or '']
            else:
                continue        # 相对导入（from .x import y）必然是本地模块
            for name in names:
                top = name.split('.')[0]
                if not top or top.startswith('_') or top in local:
                    continue
                if top in sys.stdlib_module_names:
                    continue
                found.setdefault(top, set()).add(path.relative_to(BACKEND).as_posix())
    return found


def test_every_third_party_import_is_declared():
    declared = _declared_packages()
    imported = _third_party_imports()

    # 防"空过"：扫描逻辑自己坏了（比如 rglob 写错）会让用例永远绿。
    # 本仓吃过这个亏 —— ruff.toml 里记的那两条都是"检查一直空过"。
    assert len(imported) > 15, f'只扫到 {len(imported)} 个第三方 import，扫描逻辑可疑'

    undeclared = {
        name: sorted(files)
        for name, files in imported.items()
        if _normalize(IMPORT_TO_PACKAGE.get(name, name)) not in declared
    }
    assert not undeclared, (
        'backend/requirements.txt 缺少以下声明（import 名 → 出现位置）：\n'
        + '\n'.join(f'  {name}  ←  {", ".join(files)}'
                    for name, files in sorted(undeclared.items()))
        + '\n\n若某名字是本地模块，请确认它真的在 backend/ 顶层；'
          '若 import 名与 PyPI 发行名不同（如 cv2 / opencv-python），'
          '把它加进本文件的 IMPORT_TO_PACKAGE。'
    )
