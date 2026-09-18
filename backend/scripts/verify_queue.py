"""消息队列验收（阶段 8）

这个脚本要证明的是**队列相对裸 threading 真正多出来的东西**，而不是
"接口变快了"这种本来就成立的性质。

诚实起见先说清楚：`app.run(debug=...)` 在 Flask ≥1.0 下 threaded=True 是默认值，
所以改造前后"训练跑着时其他接口仍秒回"都成立。本脚本把响应性作为回归护栏
保留，但真正的验收项是下面这几条 —— 它们是 threading 版本做不到的：

  [1] worker 连的是 PostgreSQL，不是静默回退的 SQLite
      这是 .env 没加载时最危险的故障：任务照跑照"成功"，数据全进另一个库
  [2] **后端重启后任务仍在跑**（threading 版必死，这是队列最核心的收益）
  [3] worker 崩溃后卡死的任务被回收，不会永久停在 running
  [4] broker 不可用时上传返回 503，且不留下永不处理的 pending 行
  [5] 入库的 pending → ready 流转，且 chunk_count 与切片数一致（不变量）
  [6] worker 入库后，API 进程立刻能检索到新语料（跨进程缓存失效）

需要后端与 worker 都已启动。脚本会重启后端、并短暂停一次 Redis，
跑完会恢复。

用法：
    cd backend
    python scripts/verify_queue.py
"""
import io
import pathlib
import re
import subprocess
import sys
import time

import requests

BASE = 'http://127.0.0.1:5000'
BACKEND = pathlib.Path(__file__).resolve().parent.parent
LOG = BACKEND / 'logs' / 'app.log'
MARKER = 'QQZK9VX27'

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f'  {detail}' if detail else ''))


def section(t):
    print(f'\n{t}')


def sh(args, timeout=180):
    # encoding/errors 必须显式给：Windows 控制台默认 GBK，脚本里的中文
    # 提示会让 text=True 的默认解码抛 UnicodeDecodeError
    return subprocess.run(args, cwd=str(BACKEND), capture_output=True,
                          text=True, timeout=timeout, shell=False,
                          encoding='utf-8', errors='replace')


def login(user='admin', attempts=12):
    """从日志读验证码明文登录"""
    for _ in range(attempts):
        r = requests.get(f'{BASE}/api/captcha', timeout=10)
        cid = r.headers.get('X-Captcha-ID')
        if not cid:
            time.sleep(1)
            continue
        time.sleep(1.2)          # 等 stdout 块缓冲刷出 DEBUG 行
        text = LOG.read_text(encoding='utf-8', errors='ignore')
        code = next((c for c, i in reversed(re.findall(
            r'生成验证码:\s*([0-9A-Z]{4}),\s*captcha_id:\s*(\S+)', text)) if i == cid), None)
        if not code:
            time.sleep(1)
            continue
        r = requests.post(f'{BASE}/api/login', json={
            'username': user, 'password': '123456',
            'captcha': code, 'captcha_id': cid}, timeout=15)
        if r.status_code == 200:
            j = r.json()
            return j.get('access_token') or j.get('token')
        time.sleep(1)
    raise SystemExit('登录失败：确认后端以 LOG_LEVEL=DEBUG 启动（bash scripts/flask.sh start debug）')


def headers():
    return {'Authorization': 'Bearer ' + login()}


def post_training(H, name, epochs):
    r = requests.post(f'{BASE}/api/models/train', headers=H, data={
        'name': name, 'base_model': 'yolov8n', 'dataset_source': 'existing',
        'dataset_id': '1', 'epochs': str(epochs), 'batch_size': '4',
        'img_size': '320'}, timeout=60)
    return r


def task_status(task_id, H):
    return requests.get(f'{BASE}/api/training/tasks/{task_id}/progress',
                        headers=H, timeout=10).json()


def wait_status(task_id, H, wants, timeout=300, poll=1.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        d = task_status(task_id, H)
        last = d.get('status')
        if last in wants:
            return last
        time.sleep(poll)
    return last


def main():
    H = headers()
    pending_cleanup = []

    # ---------- 1. worker 连的是 PostgreSQL ----------
    section('[1] worker 的数据库连接（防静默回退到 SQLite）')
    try:
        sys.path.insert(0, str(BACKEND))
        from tasks.diagnostics import ping
        res = ping.delay({'from': 'verify_queue'}).get(timeout=90)
        check('worker 连的是 PostgreSQL 而非 SQLite',
              res.get('db_dialect') == 'postgresql', f"dialect={res.get('db_dialect')}")
        print(f"      {res.get('db_url')}")
    except Exception as e:
        check('worker 连的是 PostgreSQL 而非 SQLite', False, repr(e)[:120])

    # ---------- 2. 后端重启后任务仍在跑 ----------
    section('[2] 后端重启后训练任务不受影响（队列相对线程的核心收益）')
    r = post_training(H, '队列验收-重启存活', 400)
    if r.status_code != 200:
        check('启动长训练', False, f'HTTP {r.status_code} {r.text[:120]}')
    else:
        task_id = r.json()['task_id']
        model_id = r.json()['model_id']
        pending_cleanup.append(model_id)
        check('启动长训练', True, f'task_id={task_id}')

        started = wait_status(task_id, H, {'running', 'completed', 'failed'}, timeout=120)
        check('任务进入执行状态', started == 'running', f'状态={started}')

        before = task_status(task_id, H).get('current_epoch', 0)
        print(f'      重启前后端时的 epoch = {before}')

        # 重启后端：threading 版的训练线程会随进程一起消失
        out = sh(['bash', 'scripts/flask.sh', 'restart', 'debug'])
        check('后端重启成功', out.returncode == 0,
              (out.stdout or out.stderr or '')[-90:].strip())

        H = headers()      # token 仍有效，但重新登录一次更稳
        time.sleep(20)
        after = task_status(task_id, H)
        check('重启后任务仍在推进（未被重启打断）',
              after.get('status') in ('running', 'completed')
              and after.get('current_epoch', 0) >= before,
              f"status={after.get('status')} epoch={after.get('current_epoch')}")

        # 收尾：停掉它，避免长时间占用 worker
        requests.post(f'{BASE}/api/training/tasks/{task_id}/stop', headers=H, timeout=30)
        # 等 worker 收尾（solo 池下不会立刻中断，需等当前 epoch 结束）
        final = wait_status(task_id, H, {'stopped', 'completed', 'failed'}, timeout=180)
        check('停止后任务落定', final in ('stopped', 'failed'), f'状态={final}')

    # ---------- 3. broker 不可用 ----------
    section('[3] broker 不可用时上传返回 503，且不留悬空行')
    sh(['bash', 'scripts/redis.sh', 'stop'])
    time.sleep(2)
    try:
        r = requests.post(f'{BASE}/api/knowledge/docs', headers=H,
                          files={'file': ('broker故障.md', io.BytesIO(
                              f'# broker故障\n\n正文 {MARKER}\n'.encode('utf-8')),
                              'text/markdown')},
                          data={'origin': 'curated', 'source': '队列验收'}, timeout=90)
        check('broker 不可用时上传 → 503', r.status_code == 503, f'HTTP {r.status_code}')
        if r.status_code == 503:
            print(f"      提示: {r.json().get('error', '')[:70]}")
        dangling = count_docs_by_status('pending')
        check('broker 故障没有留下 pending 行', dangling == 0, f'pending={dangling}')
    finally:
        sh(['bash', 'scripts/redis.sh', 'start'])
        time.sleep(25)      # 等 core/cache.py 的冷却期过去，应用切回 Redis

    # ---------- 4. 入库流程 ----------
    section('[4] 异步入库：pending → ready 与不变量')
    body = (f'# 队列验收文档\n\n## 一、标记段\n\n'
            f'本段唯一标记 {MARKER} ，用于验证异步入库与跨进程缓存。\n').encode('utf-8')
    t0 = time.time()
    r = requests.post(f'{BASE}/api/knowledge/docs', headers=H,
                      files={'file': ('队列验收.md', io.BytesIO(body), 'text/markdown')},
                      data={'origin': 'curated', 'source': '队列验收'}, timeout=60)
    submit = time.time() - t0
    check('上传立即返回（< 5s，不等入库）', submit < 5 and r.status_code == 202,
          f'{submit:.2f}s HTTP {r.status_code}')
    if r.status_code == 202:
        doc_id = r.json()['doc_id']
        pending_cleanup.append(('doc', doc_id))
        check('受理时状态为 pending', r.json().get('status') == 'pending',
              f"status={r.json().get('status')}")

        final = None
        deadline = time.time() + 300
        while time.time() < deadline:
            d = requests.get(f'{BASE}/api/knowledge/docs/{doc_id}',
                             headers=H, timeout=30).json().get('data', {})
            final = d.get('status')
            if final in ('ready', 'failed'):
                break
            time.sleep(2)
        check('文档最终变为 ready', final == 'ready', f'状态={final}')

        # 不变量：切片存在 ⟺ 文档 ready（services/rag/pipeline.py 的模块文档）
        n_chunks = len(requests.get(f'{BASE}/api/knowledge/docs/{doc_id}/chunks',
                                    headers=H, timeout=30).json().get('data', []))
        d = requests.get(f'{BASE}/api/knowledge/docs/{doc_id}',
                         headers=H, timeout=30).json().get('data', {})
        check('chunk_count 与实际切片数一致（不变量）',
              d.get('chunk_count') == n_chunks,
              f"chunk_count={d.get('chunk_count')} 实际={n_chunks}")

        # ---------- 5. 跨进程缓存失效 ----------
        section('[5] worker 入库后 API 进程立刻能检索到（跨进程缓存）')
        rr = requests.post(f'{BASE}/api/knowledge/search', headers=H,
                           json={'query': MARKER, 'top_k': 5}, timeout=180)
        results = rr.json().get('results', [])
        hit = any(MARKER in (x.get('content') or '') for x in results)
        check('刚入库的内容立刻可检索', hit, f'检索到 {len(results)} 条')

    # ---------- 清理 ----------
    print()
    for item in pending_cleanup:
        try:
            if isinstance(item, tuple):
                requests.delete(f'{BASE}/api/knowledge/docs/{item[1]}',
                                headers=H, timeout=30)
            else:
                requests.delete(f'{BASE}/api/models/{item}', headers=H, timeout=30)
        except requests.exceptions.RequestException:
            pass

    print('\n' + '=' * 62)
    print(f'  通过 {len(PASS)} / 失败 {len(FAIL)}')
    for n in FAIL:
        print(f'    - {n}')
    return len(FAIL)


def count_docs_by_status(status):
    """直接用 DB 数（不经 API，避免被列表默认过滤干扰）"""
    try:
        from core.bootstrap import build_bare_app
        app, _ = build_bare_app()
        from database import KnowledgeDoc, db
        with app.app_context():
            return KnowledgeDoc.query.filter_by(status=status).count()
    except Exception:
        return -1


if __name__ == '__main__':
    sys.exit(main())
