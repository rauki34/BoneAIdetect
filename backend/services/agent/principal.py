"""Agent 调用者身份与患者解析

`Principal` 只持有 primitives（id / role / username），**不持有 ORM 对象**，
这不是洁癖，有三条实际理由：

1. `core.helpers.can_access_patient` 只读 `user.role` 与 `user.id`，鸭子类型
   完全兼容 —— 因此**不需要为了测试去改那个权限函数一行**。
2. 工具层因此可以脱离 Flask 与数据库做确定性单测：验证脚本直接构造
   `Principal(1, 'patient', 'p1')` 就能跑权限分支。
3. 若将来把编排搬进生成器或线程（请求上下文之外），ORM 对象绑在旧 session 上，
   跨上下文使用会炸；primitives 不会。
"""
from dataclasses import dataclass

from core.helpers import can_access_patient


@dataclass(frozen=True)
class Principal:
    """Agent 的调用者"""
    id: int
    role: str                  # 'patient' | 'doctor' | 'admin'
    username: str = ''

    @classmethod
    def of(cls, user) -> 'Principal':
        """从 ORM User 对象构造（视图层用）"""
        return cls(id=user.id, role=user.role, username=user.username or '')


def err(code, message):
    """工具的错误返回（封闭枚举见 tools.py 的模块文档）"""
    return {'error': code, 'message': message}


def resolve_patient(principal, args, *, required=True):
    """把 args['patient_id'] 解析成**已授权**的 patient_id

    返回 (patient_id, error)：error 非 None 时调用方原样返回它。

    三种入参的处理：
      - 不传 + 患者     → 自己的 id，天然合法（不查库）
      - 不传 + 医生/管理员 + required → missing_patient_id（**绝不默认"全部患者"**）
      - 不传 + required=False → (None, None)，调用方自行决定只查共享库
      - 传了             → 一律过 can_access_patient（core/helpers.py:15）

    **为什么权限必须在工具内部做**：编排层不知道模型下一步会传哪个 patient_id
    （它是 LLM 生成的），视图层只能校验请求入口那一个。唯一能覆盖"模型任意
    生成参数"的拦截点就是这里 —— 把越权判断交给 LLM 提示词是无效的。
    """
    raw = (args or {}).get('patient_id')
    if raw in (None, '', 0):
        if principal.role == 'patient':
            return principal.id, None
        if required:
            return None, err(
                'missing_patient_id',
                '未指定患者。请先向用户确认要查询哪位患者（患者ID），'
                '再调用本工具。')
        return None, None
    try:
        pid = int(raw)
    except (TypeError, ValueError):
        return None, err('invalid_arguments', 'patient_id 必须是整数')
    if not can_access_patient(principal, pid):
        # 与「查无数据」严格区分：调用方（含模型）必须能看出这是被拒绝，
        # 而不是"这位患者没有资料"——后者会让模型编造一个解释
        return None, err('permission_denied', '无权访问该患者的数据')
    return pid, None
