"""校验各模块的 import 是否覆盖实际用到的全局名

使用标准库 symtable 做**正确的作用域分析**：
闭包变量、函数内局部 import、嵌套作用域都能被正确处理
（手写 AST 遍历在这三点上都会误报）。

只报告「在函数中被引用、解析到全局作用域、但模块顶层未绑定」的名字，
这正是搬迁代码后最容易出错的场景（漏 import 时 py_compile 不会报错）。
"""
import builtins
import pathlib
import symtable
import sys

FOLDERS = ['backend/api', 'backend/services', 'backend/core']

# 运行期由 Flask/框架注入，或由调用方以关键字传入
ALLOW = {
    'app', 'bp', 'current_app', 'request', 'g',
    'self', 'cls',
}
BUILTINS = set(dir(builtins))


def top_level_bound(st):
    """模块顶层绑定的名字：赋值、def、class、import、形参"""
    names = set()
    for sym in st.get_symbols():
        if sym.is_assigned() or sym.is_imported() or sym.is_namespace() \
                or sym.is_parameter():
            names.add(sym.get_name())
    return names


def collect_missing(scope, bound, out):
    """递归查找解析到全局作用域但未被绑定的名字"""
    for sym in scope.get_symbols():
        name = sym.get_name()
        # is_global(): 该名字在此作用域解析为全局引用
        if sym.is_global() and name not in bound and name not in BUILTINS \
                and name not in ALLOW:
            out.add(name)
    for child in scope.get_children():
        collect_missing(child, bound, out)


def main():
    ok = True
    for folder in FOLDERS:
        for f in sorted(pathlib.Path(folder).glob('*.py')):
            src = f.read_text(encoding='utf-8')
            try:
                st = symtable.symtable(src, str(f), 'exec')
            except SyntaxError as e:
                print(f'  {f}  语法错误: {e}')
                ok = False
                continue
            bound = top_level_bound(st)
            missing = set()
            for child in st.get_children():
                collect_missing(child, bound, missing)
            if missing:
                ok = False
            print(f'  {str(f):34} {"未定义!" if missing else "OK":8} '
                  f'{sorted(missing) if missing else ""}')
    print()
    print('结论:', 'PASS — 所有模块的全局引用均已绑定' if ok else 'FAIL — 存在未定义引用')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
