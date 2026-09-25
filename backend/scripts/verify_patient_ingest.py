"""患者病历自动切片回归验证（阶段 12）

覆盖：医生保存/更新病历时自动投递切片任务、切片内容随之更新、
**过期版本被清理（不留重复）**、以及"队列不可用时保存病历仍然成功"。

## 为什么单独一个脚本

它验的是**跨组件的链路**：医生端 API → Celery 队列 → worker → RAG 管线 → 索引。
每一步单独看都是好的，缺的是"接线"—— 而这条线在阶段 12 之前**根本没接**：
`ingest_patient_records` 全后端只有 `scripts/ingest_knowledge.py` 一个调用点，
医生改了病历之后知识库里的个人切片还是旧的。

## 前提

- 后端（debug 模式）与 **Celery worker** 都要在跑：切片在 worker 里做，
  只起后端的话文档会永远停在 pending（记忆里最容易漏的一步）
- 用真实的医生与患者账号；测试数据全部自造自清（记录号带唯一前缀）

用法：
    cd backend
    python scripts/verify_patient_ingest.py [日志文件路径]

退出码 = 失败用例数。
"""
import pathlib
import re
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

BASE = 'http://127.0.0.1:5000'
LOG = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else \
    pathlib.Path(__file__).resolve().parent.parent / 'logs' / 'app.log'
PASSWORD = '123456'
# 唯一标记：切片内容里必须出现它，用来证明"检索到的是这一版"
MARK_OLD = 'VERIFY_旧版诊断_不可检索'
MARK_NEW = 'VERIFY_新版诊断_应可检索'

PASS, FAIL, SKIP = [], [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f'  {detail}' if detail else ''))


def skip(name, why):
    SKIP.append(name)
    print(f'  [SKIP] {name}  {why}')


def section(title):
    print(f'\n{title}')


def login(user, attempts=12):
    for _ in range(attempts):
        r = requests.get(f'{BASE}/api/captcha', timeout=10)
        cid = r.headers.get('X-Captcha-ID')
        if not cid:
            time.sleep(1)
            continue
        time.sleep(1.2)
        text = LOG.read_text(encoding='utf-8', errors='ignore')
        code = next((c for c, i in reversed(re.findall(
            r'生成验证码:\s*([0-9A-Z]{4}),\s*captcha_id:\s*(\S+)', text)) if i == cid), None)
        if not code:
            time.sleep(1)
            continue
        r = requests.post(f'{BASE}/api/login', json={
            'username': user, 'password': PASSWORD,
            'captcha': code, 'captcha_id': cid}, timeout=15)
        if r.status_code == 200:
            j = r.json()
            return j.get('access_token') or j.get('token')
        time.sleep(1)
    raise SystemExit('登录失败：确认后端以 LOG_LEVEL=DEBUG 启动'
                     '（bash scripts/flask.sh start debug）')


def auth(tok):
    return {'Authorization': f'Bearer {tok}'}


def docs_of(app, record_id):
    """该病历派生出的知识库文档（直连 DB，比轮询接口更直接）"""
    from database import KnowledgeDoc, db
    from database import safe_json_loads
    with app.app_context():
        rows = KnowledgeDoc.query.filter_by(file_path=None).all()
        out = []
        for d in rows:
            meta = safe_json_loads(d.doc_meta, {}) or {}
            if meta.get('source_table') == 'medical_records' and \
                    str(meta.get('source_id')) == str(record_id):
                out.append({'id': d.id, 'status': d.status, 'title': d.title,
                            'chunks': d.chunk_count})
        return out


def chunk_texts_of(app, doc_ids):
    from database import KnowledgeChunk, db
    with app.app_context():
        return [c.content or '' for c in
                KnowledgeChunk.query.filter(KnowledgeChunk.doc_id.in_(doc_ids)).all()]


def wait_for(app, record_id, *, expect_status='ready', timeout=180, poll=2):
    deadline = time.time() + timeout
    docs = []
    while time.time() < deadline:
        docs = docs_of(app, record_id)
        if docs and all(d['status'] in ('ready', 'failed') for d in docs):
            return docs
        time.sleep(poll)
    return docs or docs_of(app, record_id)


def main():
    from core.bootstrap import build_bare_app, enable_utf8_console, load_env
    load_env()
    enable_utf8_console()
    app, _ = build_bare_app()

    try:
        requests.get(f'{BASE}/api/captcha', timeout=10)
    except Exception as e:
        print(f'后端未就绪（{e}）。请先：bash scripts/flask.sh start debug')
        return 1

    from database import MedicalRecord, User, db

    with app.app_context():
        doctor = User.query.filter_by(role='doctor').first()
        patient = User.query.filter_by(role='patient').first()
        if not doctor or not patient:
            print('需要至少一个医生与一个患者账号')
            return 1
        d_name, p_id, d_id = doctor.username, patient.id, doctor.id

    dtok = login(d_name)
    created_ids = []

    section('[1] 新建病历 → 自动切片')
    r = requests.post(f'{BASE}/api/doctor/medical-records', headers=auth(dtok), json={
        'patient_id': p_id,
        'diagnosis': MARK_OLD,
        'symptoms': '验证脚本造的数据',
        'treatment': '无需处理',
        'advice': '验证用',
    }, timeout=30)
    ok = r.status_code == 200 and r.json().get('success')
    check('医生创建病历成功', ok, f'HTTP {r.status_code} {r.text[:120]}')
    if not ok:
        return len(FAIL)

    with app.app_context():
        rec = MedicalRecord.query.filter_by(
            patient_id=p_id, diagnosis=MARK_OLD).order_by(
            MedicalRecord.id.desc()).first()
        if not rec:
            check('能取回刚创建的病历', False)
            return len(FAIL)
        record_id = rec.id
        created_ids.append(record_id)

    docs = wait_for(app, record_id)
    check('该病历被自动切片（工单投递 + worker 执行）',
          bool(docs), f'找到 {len(docs)} 篇派生文档')
    if not docs:
        skip('内容与清理相关用例', '切片没有产生，先确认 worker 在跑（bash scripts/celery.sh status）')
        _cleanup(app, created_ids)
        return len(FAIL)

    check('切片完成（status=ready）', all(d['status'] == 'ready' for d in docs),
          str([d['status'] for d in docs]))
    texts = chunk_texts_of(app, [d['id'] for d in docs])
    check('切片内容含该病历的诊断', any(MARK_OLD in t for t in texts),
          f'{len(texts)} 个切片')

    section('[2] 更新病历 → 切片更新，且**旧版本被清理**')
    r = requests.put(f'{BASE}/api/doctor/medical-records/{record_id}',
                     headers=auth(dtok), json={'diagnosis': MARK_NEW}, timeout=30)
    check('医生更新病历成功', r.status_code == 200, f'HTTP {r.status_code}')

    deadline = time.time() + 180
    texts, docs = [], docs
    while time.time() < deadline:
        docs = docs_of(app, record_id)
        texts = chunk_texts_of(app, [d['id'] for d in docs])
        if any(MARK_NEW in t for t in texts):
            break
        time.sleep(3)
    check('切片内容更新为新诊断', any(MARK_NEW in t for t in texts),
          f'共 {len(texts)} 个切片')
    check('**过期版本已被清理**（同一病历只剩一条派生文档）', len(docs) == 1,
          f'实际 {len(docs)} 条：{[d["id"] for d in docs]}')
    check('旧诊断不再出现在任何切片里', not any(MARK_OLD in t for t in texts),
          f'{sum(1 for t in texts if MARK_OLD in t)} 个切片仍含旧内容')

    section('[3] 队列不可用时，保存病历**仍然成功**')
    # 投递失败不该让医生保存不了病历 —— 知识库陈旧是可接受的，保存失败不是。
    # 这里不停 Redis（会波及其他用例），而是直接验证辅助函数的行为。
    from api.doctor import _enqueue_patient_ingest
    import tasks.knowledge as kb_task
    original = kb_task.ingest_patient_records_task.delay
    try:
        kb_task.ingest_patient_records_task.delay = _raise_broker_down
        _enqueue_patient_ingest(record_id, username='verify')   # 不应抛异常
        check('投递失败时辅助函数不抛异常（业务不受影响）', True)
    except Exception as e:      # noqa: BLE001
        check('投递失败时辅助函数不抛异常（业务不受影响）', False, repr(e)[:100])
    finally:
        kb_task.ingest_patient_records_task.delay = original

    section('[4] 数据隔离：该派生文档只属于该患者')
    with app.app_context():
        from database import KnowledgeDoc
        doc = db.session.get(KnowledgeDoc, docs[0]['id']) if docs else None
        check('派生文档带 patient_id（检索层据此强制过滤）',
              doc is not None and doc.patient_id == p_id,
              f'patient_id={getattr(doc, "patient_id", None)}')
        check('派生文档有出处（引用卡片才不会显示空来源）',
              bool(doc and doc.source), f'source={getattr(doc, "source", None)!r}')

    section('[5] 清理验证数据')
    _cleanup(app, created_ids)
    print(f'  已删除 {len(created_ids)} 条测试病历及其派生文档')

    print('\n' + '=' * 62)
    print(f'  通过 {len(PASS)} / 失败 {len(FAIL)} / 跳过 {len(SKIP)}')
    for n in FAIL:
        print(f'    - {n}')
    for n in SKIP:
        print(f'    ~ {n}')
    return len(FAIL)


def _raise_broker_down(*_args, **_kwargs):
    raise ConnectionError('模拟 broker 不可用')


def _cleanup(app, record_ids):
    """删掉测试病历**及其派生文档**（后者要手动删：没有接口会替我们做）"""
    from database import KnowledgeChunk, KnowledgeDoc, MedicalRecord, db, safe_json_loads
    with app.app_context():
        for rid in record_ids:
            rec = db.session.get(MedicalRecord, rid)
            if rec:
                db.session.delete(rec)
            for doc in KnowledgeDoc.query.filter_by(file_path=None).all():
                meta = safe_json_loads(doc.doc_meta, {}) or {}
                if meta.get('source_table') == 'medical_records' and \
                        str(meta.get('source_id')) == str(rid):
                    KnowledgeChunk.query.filter_by(doc_id=doc.id).delete()
                    db.session.delete(doc)
        db.session.commit()


if __name__ == '__main__':
    sys.exit(main())
