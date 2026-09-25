"""Agent 工具集（阶段 9，患者康复助手）

设计原则：
1. 每个工具用 JSON Schema 描述自己，交给模型理解（`tool_schemas()`）
2. **权限校验发生在工具内部**，不交给 LLM（见 principal.resolve_patient）
3. 失败返回 `{'error': ...}` 而不是抛异常 —— 模型看到错误可以换策略，
   而异常会终止整条编排
4. 返回值必须 JSON 可序列化，时间一律本地化

错误码是**封闭枚举**，其中「权限拒绝」与「查无数据」必须可区分：
「返回空」在越权、库里真没有、服务挂了三种情况下现象完全一样，压成同一个
返回值就只能测 HTTP 200 —— 而那正是最没信息量的判据。

    permission_denied   有权限体系但校验失败
    not_found           有权限但查无数据
    unsupported         环境不支持（总开关关闭 / 检索熔断）
    invalid_arguments   参数类型或取值不合法（含 JSON 解析失败）
    missing_patient_id  需要患者但未指定（医生/管理员）
    unknown_tool        工具名不存在
    duplicate           同名同参重复调用
    internal_error      兜底

五个工具都是**只读**的。这不是保守，而是刻意的边界：让 LLM 自主触发写操作
（重跑检测、改病历）意味着把"谁在什么时候对哪张片子做了什么"交给模型决定，
而医疗场景要求检测由医生在检测页面发起、审计链完整。
"""
import datetime
import hashlib
import json
import os

from config import config               # 模块里的 config 是配置实例（config.py 末尾）
from database import (DetectionHistory, MedicalRecord, PatientProfile, User,
                      db, get_display_name, safe_json_loads, to_local_time)
from services.agent.principal import err, resolve_patient

# ==================== 注册机制 ====================


class ToolSpec:
    __slots__ = ('name', 'description', 'parameters', 'handler', 'requires_patient')

    def __init__(self, name, description, parameters, handler, requires_patient):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler
        self.requires_patient = requires_patient


TOOL_REGISTRY = {}


def tool(name, description, parameters, *, requires_patient=False):
    """注册工具。重名直接抛 —— 在 import 期暴露，而不是运行时静默覆盖"""
    def decorator(fn):
        if name in TOOL_REGISTRY:
            raise ValueError(f'工具重名: {name}（已存在同名工具）')
        TOOL_REGISTRY[name] = ToolSpec(name, description, parameters, fn,
                                       requires_patient)
        return fn
    return decorator


def tool_schemas(names=None):
    """转成 OpenAI tools 参数形态"""
    keys = names or list(TOOL_REGISTRY)
    return [{'type': 'function', 'function': {
                'name': TOOL_REGISTRY[k].name,
                'description': TOOL_REGISTRY[k].description,
                'parameters': TOOL_REGISTRY[k].parameters,
            }} for k in keys]


# ==================== 通用工具函数 ====================

def _clamp_int(value, *, default, lo, hi):
    """把模型给的数字收敛到合法区间（模型经常给超范围的 top_k/limit）"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _jsonable(value):
    """把 ORM 对象/特殊类型转成 JSON 安全的结构

    时间只用 `to_local_time()`（database.py:15）：库里全存 naive UTC，
    裸 `isoformat()` 会差 8 小时，而工具结果直接进 prompt —— 差 8 小时会让
    模型把"明天复诊"算错一天。
    """
    if isinstance(value, (datetime.datetime, datetime.date)):
        return to_local_time(value) if isinstance(value, datetime.datetime) \
            else value.isoformat()
    if hasattr(value, 'to_dict') and not isinstance(value, dict):
        return _jsonable(value.to_dict())
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _truncate(result, limit):
    """把结果压到 limit 字符以内，**且保持 JSON 可解析**

    不能简单截断 JSON 字符串（那会产出非法 JSON 让模型更困惑）。
    顺序：先砍长字符串字段，再按元素个数砍列表字段。
    """
    if _size(result) <= limit:
        return result

    def shrink(node, depth=0):
        if isinstance(node, dict):
            return {k: (v[:800] + '…（已截断）' if isinstance(v, str) and len(v) > 800
                        else shrink(v, depth + 1)) for k, v in node.items()}
        if isinstance(node, list):
            items = [shrink(v, depth + 1) for v in node]
            if depth <= 1 and len(items) > 1:
                items = items[:max(1, len(items) // 2)]
            return items
        return node

    for _ in range(8):
        result = shrink(result)
        if _size(result) <= limit:
            return result
    result['truncated'] = True
    return result


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, default=str))


def _fingerprint(name, args):
    raw = json.dumps([name, args], ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]


# ==================== 工具实现 ====================

@tool(
    name='search_guideline',
    description=(
        '检索骨科诊疗指南、骨折分型标准与康复规范。回答医学知识类问题'
        '（分型标准、愈合与负重时间、康复训练原则）时必须先调用本工具。'
        '只检索共享知识库，**不含任何患者个人数据**（患者本人的病历请用 '
        'query_medical_records）。'
        '返回 error=not_found 表示知识库中确实没有相关资料'
        '（已按相关度阈值过滤，与问题沾边的弱相关片段也不算数），此时必须'
        '如实告知用户"现有资料无法回答"，不得凭记忆编造；'
        '返回 error=unsupported 表示检索服务当前不可用，应告知用户暂时'
        '无法查证，同样不得编造。'),
    parameters={
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': '检索问题（中文）'},
            'top_k': {'type': 'integer', 'description': '返回条数，默认 4',
                      'minimum': 1, 'maximum': 10},
        },
        'required': ['query'],
    },
)
def search_guideline(principal, args):
    query = str((args or {}).get('query') or '').strip()
    if not query:
        return err('invalid_arguments', 'query 不能为空')
    if str(config.RAG_ENABLED).lower() != 'true':
        return err('unsupported', '知识库总开关已关闭，当前无法检索资料')

    # 延迟导入：retriever 顶层会 import embedder/reranker，进而把 torch
    # 拖进 Flask 启动路径（见 services/rag/__init__.py 的说明）
    from services.rag.prompts import build_references, format_context
    from services.rag.retriever import breaker_open, get_retriever, shared_scope

    top_k = _clamp_int((args or {}).get('top_k'),
                       default=config.AGENT_RAG_TOP_K, lo=1, hi=10)
    if breaker_open():
        # 断路器打开时 retrieve_safely 会直接返回 []，与"没搜到"长得一模一样
        return err('unsupported', '检索服务此前失败正在熔断，请稍后再试')

    chunks = get_retriever().retrieve_safely(query, scope=shared_scope(),
                                             top_k=top_k)
    if not chunks:
        # 熔断可能就在这次调用期间才打开：再探一次，免得把"服务挂了"
        # 说成"知识库没这条"
        if breaker_open():
            return err('unsupported', '检索服务不可用，请稍后再试')
        return err('not_found', '知识库中没有找到相关资料')

    # **相关度阈值**：向量检索是最近邻，无论问什么都会凑满 top_k —— 问"骨肉瘤
    # 的 Enneking 分期"（本语料没有）也会返回几条分数 0.006 的无关片段。若不
    # 拦截，模型会把它们当成依据来作答，而工具契约里的 not_found 就永远不可达。
    # 实测本语料的分数两极分化：真命中 ≥ 0.9，缺题 ≤ 0.2，阈值取中间。
    best = max((c.score or 0.0) for c in chunks)
    if best < config.AGENT_RAG_MIN_SCORE:
        return err('not_found',
                   f'知识库中没有与该问题相关的资料（最高相关度 {best:.2f}，'
                   f'低于阈值 {config.AGENT_RAG_MIN_SCORE}）')
    return {
        'count': len(chunks),
        'context': format_context(chunks),          # 给模型读的正文
        'results': [_chunk_brief(c) for c in chunks],  # 给 trace 看的摘要
        '_references': build_references(chunks),    # 侧信道：6 键引用契约
    }


@tool(
    name='query_medical_records',
    description=(
        '查询患者本人的既往病历与医嘱（诊断、症状、治疗、用药、医嘱、复诊日期）。'
        '回答"我之前诊断出什么问题""医生让我注意什么""下次什么时候复诊"这类'
        '问题时调用。**默认只返回有效病历**；已删除的病历永远不会返回。'),
    parameters={
        'type': 'object',
        'properties': {
            'patient_id': {'type': 'integer',
                           'description': '患者ID；患者本人查询时可不填'},
            'limit': {'type': 'integer', 'description': '返回条数，默认 5',
                      'minimum': 1, 'maximum': 20},
            'include_archived': {'type': 'boolean',
                                 'description': '是否包含已归档病历，默认 false'},
        },
        'required': [],
    },
    requires_patient=True,
)
def query_medical_records(principal, args):
    pid, e = resolve_patient(principal, args)
    if e:
        return e
    limit = _clamp_int((args or {}).get('limit'), default=5, lo=1, hi=20)
    statuses = ['active', 'archived'] if (args or {}).get('include_archived') \
        else ['active']

    # 永不含 'deleted'：已删除病历进 LLM 上下文是合规问题。
    # 注意 api/patient.py 的同名查询**不过滤 status**，那是既有缺陷，
    # 不要在工具里复制它。
    rows = (MedicalRecord.query
            .filter(MedicalRecord.patient_id == pid,
                    MedicalRecord.status.in_(statuses))
            # 加 id 兜底排序：同一天多条时顺序不稳定，两次调用结果不一致
            # 会让模型对同一问题给出不同答案
            .order_by(MedicalRecord.visit_date.desc(), MedicalRecord.id.desc())
            .limit(limit).all())
    if not rows:
        return err('not_found', '该患者没有病历记录（或病历均已归档/删除）')
    return {'count': len(rows), 'items': [_record_brief(r) for r in rows]}


@tool(
    name='get_patient_profile',
    description=(
        '查询患者本人的档案：过敏史与既往病史（均为自由文本，可能未填写）。'
        '给出任何用药或康复建议之前，应先调用本工具确认有无过敏史。'
        '本工具**不返回**身份证号、住址、紧急联系人等隐私字段。'),
    parameters={
        'type': 'object',
        'properties': {
            'patient_id': {'type': 'integer',
                           'description': '患者ID；患者本人查询时可不填'},
        },
        'required': [],
    },
    requires_patient=True,
)
def get_patient_profile(principal, args):
    pid, e = resolve_patient(principal, args)
    if e:
        return e
    user = db.session.get(User, pid)
    if user is None:
        return err('not_found', '患者账号不存在')
    base = {'name': user.full_name or user.username}

    profile = PatientProfile.query.filter_by(user_id=pid).first()
    if profile is None:
        # PatientProfile 是**可选**的（api/patient.py:126 也处理了这种情况），
        # 直接 .to_dict() 会 AttributeError
        return {'count': 0, 'profile': base,
                'note': '该患者尚未建立档案，没有过敏史与既往史记录'}

    # 白名单式取字段，而不是 to_dict() 后删隐私字段：漏删一个就是病历出境，
    # 而漏加一个业务字段只是少点信息。这两种错误的代价不对称。
    return {'count': 1, 'profile': {
        **base,
        'gender': profile.gender,
        'birth_date': profile.birth_date.isoformat() if profile.birth_date else None,
        'allergies': profile.allergies,
        'medical_history': profile.medical_history,
        'note': '过敏史与既往史为自由文本录入，可能未填写或不完整',
    }}


@tool(
    name='list_detection_reports',
    description=(
        '列出**已归属到该患者账号**的影像检测报告（骨折类型、置信度、检测时间、'
        '是否已有 AI 解读）。回答"我的片子结果怎么样""复查结果如何"时调用。'
        '注意：历史数据可能尚未归属到账号，此时会返回 error=not_found —— '
        '这表示"没有归属到本人的记录"，不代表该患者从未做过检测。'),
    parameters={
        'type': 'object',
        'properties': {
            'patient_id': {'type': 'integer',
                           'description': '患者ID；患者本人查询时可不填'},
            'limit': {'type': 'integer', 'description': '返回条数，默认 5',
                      'minimum': 1, 'maximum': 20},
        },
        'required': [],
    },
    requires_patient=True,
)
def list_detection_reports(principal, args):
    pid, e = resolve_patient(principal, args)
    if e:
        return e
    limit = _clamp_int((args or {}).get('limit'), default=5, lo=1, hi=20)
    rows = (DetectionHistory.query
            .filter(DetectionHistory.patient_id == pid)
            .order_by(DetectionHistory.timestamp.desc(), DetectionHistory.id.desc())
            .limit(limit).all())
    if not rows:
        return err(
            'not_found',
            '没有归属到本人的检测记录。历史检测数据可能尚未与账号关联'
            '（医生可在检测报告页把记录归属到患者），这不代表从未做过检测。')
    return {'count': len(rows), 'items': [_report_brief(r) for r in rows]}


@tool(
    name='get_followup_schedule',
    description=(
        '查询患者本人的复诊/随访安排，返回已过期（overdue）与即将到来'
        '（upcoming）两类。回答"我什么时候复诊""该复查了吗"时调用。'
        '**本系统没有独立的随访计划表**，复诊日期来自病历医嘱字段，'
        '可能未填写；返回 error=not_found 即表示没有已填写的复诊日期。'),
    parameters={
        'type': 'object',
        'properties': {
            'patient_id': {'type': 'integer',
                           'description': '患者ID；患者本人查询时可不填'},
            'days': {'type': 'integer',
                     'description': '未来多少天内算"即将到来"，默认 30，最大 365',
                     'minimum': 1, 'maximum': 365},
        },
        'required': [],
    },
    requires_patient=True,
)
def get_followup_schedule(principal, args):
    pid, e = resolve_patient(principal, args)
    if e:
        return e
    days = _clamp_int((args or {}).get('days'), default=30, lo=1, hi=365)
    now = datetime.datetime.utcnow()          # 库里存 naive UTC
    horizon = now + datetime.timedelta(days=days)

    rows = (MedicalRecord.query
            .filter(MedicalRecord.patient_id == pid,
                    MedicalRecord.status != 'deleted',
                    MedicalRecord.follow_up_date.isnot(None))
            .order_by(MedicalRecord.follow_up_date.asc())
            .all())
    overdue, upcoming = [], []
    for r in rows:
        item = {'record_id': r.id, 'diagnosis': r.diagnosis,
                'visit_date': to_local_time(r.visit_date),
                'follow_up_date': to_local_time(r.follow_up_date)}
        if r.follow_up_date < now:
            overdue.append(item)
        elif r.follow_up_date <= horizon:
            upcoming.append(item)
        # 超出 days 的更远日期不返回，否则一年后的复诊也会被塞进"即将到来"

    notes = [{'timestamp': to_local_time(r.timestamp),
              'follow_up_notes': r.follow_up_notes}
             for r in (DetectionHistory.query
                       .filter(DetectionHistory.patient_id == pid,
                               DetectionHistory.follow_up_notes.isnot(None))
                       .order_by(DetectionHistory.timestamp.desc())
                       .limit(5).all()) if r.follow_up_notes]

    if not overdue and not upcoming and not notes:
        return err('not_found',
                   '没有已填写的复诊日期或随访备注（病历医嘱里未填写复诊时间）')
    return {'overdue': overdue, 'upcoming': upcoming, 'notes': notes,
            'horizon_days': days,
            'note': '复诊日期来自病历医嘱字段，可能未填写或不完整'}


# ==================== 结果的紧凑视图 ====================

def _chunk_brief(chunk):
    return {'doc': chunk.doc_title, 'section': chunk.section,
            'score': round(chunk.score, 4) if isinstance(chunk.score, float) else chunk.score}


def _record_brief(record):
    return {
        'record_number': record.record_number,
        'visit_date': to_local_time(record.visit_date),
        'doctor': get_display_name(record.doctor) if record.doctor else None,
        'diagnosis': record.diagnosis,
        'symptoms': record.symptoms,
        'treatment': record.treatment,
        'prescription': safe_json_loads(record.prescription, None),
        'advice': record.advice,
        'follow_up_date': to_local_time(record.follow_up_date),
        'status': record.status,
    }


def _report_brief(report):
    """检测报告的紧凑视图

    刻意丢弃 `result_image` / `original_image`（是完整 URL，对模型无意义且
    占 token）与 `medical_advice` 全文（可能几千字，只给是否有）。
    """
    d = report.to_dict()
    return {
        'id': d.get('id'),
        'timestamp': d.get('timestamp'),
        'model': d.get('model'),
        'count': d.get('count'),
        'confidence': d.get('confidence'),
        'fracture_types': d.get('fracture_types'),
        'diagnosis': d.get('diagnosis'),
        'follow_up_notes': d.get('follow_up_notes'),
        'has_medical_advice': bool(d.get('medical_advice')),
    }


# ==================== 执行入口 ====================

def execute_tool(call, state):
    """执行一次工具调用。**永不抛异常**，一切失败都变成 {'error': ...}

    这是整条链路上唯一的 try/except 边界。
    返回值里**不含** `_references`：它会被摘出来并进 state.references，
    避免把几十 KB 的引用结构塞进模型上下文。
    """
    spec = TOOL_REGISTRY.get(call.name)
    if spec is None:
        return err('unknown_tool',
                   f'不存在名为 {call.name} 的工具，可选：'
                   f'{", ".join(sorted(TOOL_REGISTRY))}')
    if call.parse_error:
        return err('invalid_arguments', '参数不是合法 JSON，请重新生成参数后重试')

    fingerprint = _fingerprint(call.name, call.arguments)
    if fingerprint in state.seen_calls:
        return err('duplicate', '该工具已用相同参数调用过，请勿重复调用')
    state.seen_calls.add(fingerprint)

    try:
        result = spec.handler(state.principal, call.arguments)
        if not isinstance(result, dict):
            return err('internal_error', '工具返回了非字典结果')
        references = result.pop('_references', None)
        if references:
            state.references.extend(references)
        if result.get('error'):
            return result                      # 业务错误原样返回，不截断
        return _truncate(_jsonable(result), config.AGENT_TOOL_RESULT_MAX_CHARS)
    except Exception as e:                     # noqa: BLE001 —— 刻意兜底
        from utils.logger import logger
        logger.error('工具执行异常: %s args=%s', call.name, call.arguments,
                     exc_info=True)
        # 只回类型名，不回异常消息：消息里可能带表名/列名等实现细节
        return err('internal_error', f'工具内部错误（{type(e).__name__}），'
                                     f'请换一个思路或告知用户暂时无法查询')
