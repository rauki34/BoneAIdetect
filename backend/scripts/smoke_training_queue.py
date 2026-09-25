"""训练任务迁 Celery 的端到端冒烟

跑一次 1-epoch 的真实训练（数据集很小），验证：
  1. 投递立即返回，Web 进程不被阻塞
  2. worker 执行、进度写回 DB
  3. 训练日志文件确实被写入（前端「训练日志」弹窗的唯一数据源）
  4. 训练产出不自动进检测可用列表（发布门禁）
  5. 停止标志能真的停下任务，且状态不会被覆写成 completed

用法：
    cd backend
    python scripts/smoke_training_queue.py [--keep]
"""
import re
import sys
import time
import pathlib
import threading

import requests

BASE = 'http://127.0.0.1:5000'
# 验证码明文只能从日志读。用 utils.logger 的轮转日志而不是 stdout 重定向：
# 无论后端是 `python app.py`、nohup 还是 scripts/flask.sh 起的，它都会写这里
LOG = pathlib.Path(__file__).resolve().parent.parent / 'logs' / 'app.log'
KEEP = '--keep' in sys.argv
PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f'  [{"PASS" if cond else "FAIL"}] {name}' + (f'  {detail}' if detail else ''))


def login(user, attempts=10):
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
            'captcha': code, 'captcha_id': cid,
        }, timeout=15)
        if r.status_code == 200:
            j = r.json()
            return j.get('access_token') or j.get('token')
        time.sleep(1)
    raise SystemExit('登录失败')


class ProgressSampler(threading.Thread):
    """从**投递那一刻**起持续采样任务进度。

    为什么不能在 [2] 之后才开始轮询：1-epoch 的小数据集几秒就跑完，而 [2] 的
    响应性测量本身要花约 6.5 秒（6 次请求 + 每次 sleep 1 秒）。观测定点晚于
    训练窗口，第 [3] 段就只会看到 completed，把"没观测到"误判成"没写回 DB"。
    真正要断言的是「存在某一刻 status=running 且 0 < progress」，所以采样必须
    与训练同时开始 —— 这一点在阶段 8 假失败过两次（改小轮询间隔治不了，
    因为问题不在间隔而在起点）。
    """

    def __init__(self, task_id, H, interval=0.4):
        super().__init__(daemon=True)
        self.task_id, self.H, self.interval = task_id, H, interval
        self.saw_progress = False
        self.last = None
        self.stopped = threading.Event()

    def run(self):
        while not self.stopped.is_set():
            try:
                self.last = requests.get(
                    f'{BASE}/api/training/tasks/{self.task_id}/progress',
                    headers=self.H, timeout=10).json()
            except Exception:
                time.sleep(self.interval)
                continue
            d = self.last
            if d.get('status') == 'running' and (d.get('progress') or 0) > 0:
                self.saw_progress = True
            if d.get('status') in ('completed', 'failed', 'stopped'):
                return
            time.sleep(self.interval)

    def terminal(self):
        return (self.last or {}).get('status') in ('completed', 'failed', 'stopped')


def main():
    H = {'Authorization': 'Bearer ' + login('admin')}

    print('\n[1] 投递训练任务')
    t0 = time.time()
    r = requests.post(f'{BASE}/api/models/train', headers=H, data={
        'name': '队列冒烟-1epoch',
        'base_model': 'yolov8n',
        'dataset_source': 'existing',
        'dataset_id': '1',
        'epochs': '1',
        'batch_size': '4',
        'img_size': '320',
        'description': '阶段 8 队列迁移冒烟',
    }, timeout=60)
    submit_sec = time.time() - t0
    check('投递立即返回（< 10s）', submit_sec < 10, f'{submit_sec:.2f}s')
    check('返回 200 且带 task_id', r.status_code == 200 and r.json().get('task_id'),
          f'HTTP {r.status_code}')
    if r.status_code != 200 or not r.json().get('task_id'):
        print('   响应:', r.text[:200])
        return 1
    task_id = r.json()['task_id']
    model_id = r.json()['model_id']
    print(f'   task_id={task_id} model_id={model_id}')

    # 采样必须在投递后立刻开始：[2] 的响应性测量要花约 6.5 秒，等它跑完再采样
    # 就已经错过 1-epoch 任务的整个 running 窗口了
    sampler = ProgressSampler(task_id, H)
    sampler.start()

    # ---------- 2. 训练执行期间，Web 进程必须仍然可用 ----------
    print('\n[2] 训练执行期间 Web 进程的响应性')
    lat = []
    for _ in range(6):
        t = time.time()
        rr = requests.get(f'{BASE}/api/training/tasks', headers=H, timeout=10)
        lat.append(time.time() - t)
        assert rr.status_code == 200
        time.sleep(1)
    worst = max(lat)
    check('训练跑着时其他接口秒回（< 1s）', worst < 1.0, f'最慢 {worst:.2f}s')

    # ---------- 3. 等训练结束 ----------
    print('\n[3] 等待训练完成')
    deadline = time.time() + 900
    while time.time() < deadline and not sampler.terminal():
        time.sleep(0.5)
    sampler.stopped.set()
    last = sampler.last or {}
    status = last.get('status')
    progress = last.get('progress') or 0
    check('任务到达终态', status in ('completed', 'failed', 'stopped'), f'状态={status}')
    check('训练过程中进度被写回 DB', sampler.saw_progress, f'最后 progress={progress}')
    check('任务成功完成', status == 'completed', f'状态={status} 详情={last}')

    # ---------- 4. 训练日志文件 ----------
    print('\n[4] 训练日志（前端「训练日志」弹窗的数据源）')
    rr = requests.get(f'{BASE}/api/training/tasks/{task_id}/logs', headers=H, timeout=30)
    logs = rr.json().get('logs', '')
    check('日志接口有内容（不是"暂无日志"）', len(logs) > 200, f'{len(logs)} 字符')
    check('日志含训练开始标记', '开始训练' in logs)
    check('日志含轮次记录', 'Epoch' in logs or '训练完成' in logs)
    print(f'   日志片段: {logs[-260:].strip()[:240]!r}')

    # ---------- 5. 发布门禁 ----------
    print('\n[5] 发布门禁：训练产物不得自动进入检测可用列表')
    # 检测端的模型列表来自 /api/settings 的 available_models，它只返回
    # status='published' 的自定义模型（api/admin.py）。所以只要新模型不在里面，
    # 医生就选不到它。
    rr = requests.get(f'{BASE}/api/settings', headers=H, timeout=15)
    available = [m['key'] for m in rr.json().get('available_models', [])]

    rr = requests.get(f'{BASE}/api/models', headers=H, timeout=15)
    body = rr.json()
    models = body.get('custom_models') or body.get('models') or body.get('data') or []
    mine = next((m for m in models if m.get('id') == model_id), None)
    check('新模型状态为 trained（不是 published）',
          bool(mine) and mine.get('status') == 'trained',
          f'状态={mine and mine.get("status")}')
    check('新模型不在医生可用的检测模型列表里',
          bool(mine) and mine.get('model_key') not in available,
          f'available={available}')

    # ---------- 6. 停止语义 ----------
    # 回归一个既有 bug：原实现在 model.train() 返回后**无条件**把状态置
    # completed 并复制 best.pt。用户点停止时 trainer.stop 只是让训练提前返回，
    # 于是"已停止"会闪一下又变回"已完成"，还留下半成品权重。
    print('\n[6] 停止语义')
    r = requests.post(f'{BASE}/api/models/train', headers=H, data={
        'name': '队列冒烟-待停止',
        'base_model': 'yolov8n',
        'dataset_source': 'existing',
        'dataset_id': '1',
        'epochs': '40',
        'batch_size': '4',
        'img_size': '320',
        'description': '阶段 8 停止语义冒烟',
    }, timeout=60)
    if r.status_code != 200:
        check('启动长训练用于停止测试', False, f'HTTP {r.status_code} {r.text[:120]}')
    else:
        t2 = r.json()['task_id']
        m2 = r.json()['model_id']
        check('启动长训练用于停止测试', True, f'task_id={t2}')

        # 等它真的在跑（进度写出来过），否则测的是"撤销排队中的任务"
        started = False
        deadline = time.time() + 180
        while time.time() < deadline:
            d = requests.get(f'{BASE}/api/training/tasks/{t2}/progress',
                             headers=H, timeout=10).json()
            if d.get('status') == 'running' and (d.get('progress') or 0) > 0:
                started = True
                break
            if d.get('status') in ('completed', 'failed', 'stopped'):
                break
            time.sleep(1)
        check('任务已进入执行状态', started, '（若为 False 说明任务太快跑完，非缺陷）')

        rr = requests.post(f'{BASE}/api/training/tasks/{t2}/stop', headers=H, timeout=30)
        check('停止接口返回 200', rr.status_code == 200, f'HTTP {rr.status_code} {rr.text[:90]}')

        # 等它落地，然后**再等一会**确认没有被翻回 completed
        final = None
        deadline = time.time() + 240
        while time.time() < deadline:
            d = requests.get(f'{BASE}/api/training/tasks/{t2}/progress',
                             headers=H, timeout=10).json()
            final = d.get('status')
            if final in ('stopped', 'failed'):
                break
            time.sleep(2)
        check('最终状态是 stopped', final == 'stopped', f'状态={final}')

        # 进度在训练途中被写回 DB 的直接证据：停止时进度停在 0~100 之间，
        # 说明回调在训练过程中写过，而不是只在收尾时写了个 100
        d = requests.get(f'{BASE}/api/training/tasks/{t2}/progress',
                         headers=H, timeout=10).json()
        check('训练途中进度确实被写回 DB（epoch 回调生效）',
              0 <= (d.get('progress') or -1) < 100,
              f"progress={d.get('progress')} epoch={d.get('current_epoch')}")

        time.sleep(12)      # 给 worker 足够时间走到收尾逻辑
        again = requests.get(f'{BASE}/api/training/tasks/{t2}/progress',
                             headers=H, timeout=10).json().get('status')
        check('等待后仍是 stopped（没被 completed 覆写）', again == 'stopped',
              f'状态={again}')

        rr = requests.get(f'{BASE}/api/models', headers=H, timeout=15)
        mine2 = next((m for m in (rr.json().get('custom_models') or [])
                      if m.get('id') == m2), None)
        check('被停止的模型不产出产物（状态不是 trained）',
              bool(mine2) and mine2.get('status') != 'trained',
              f'状态={mine2 and mine2.get("status")}')

    print('\n' + '=' * 62)
    print(f'  通过 {len(PASS)} / 失败 {len(FAIL)}')
    for n in FAIL:
        print(f'    - {n}')

    if not KEEP:
        print(f'\n  （保留 task_id={task_id} model_id={model_id} 供人工核对；')
        print('    加 --keep 可跳过此提示，删除请走管理界面）')
    return len(FAIL)


if __name__ == '__main__':
    sys.exit(main())
