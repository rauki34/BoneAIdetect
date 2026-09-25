"""知识库入库任务

把「文档向量化」从 HTTP 请求里搬到 worker。搬之前，上传接口要同步跑完
解析 + 切片 + 向量化（一份 200 切片的文档约 30 秒）才返回，前端被迫设
300 秒超时，配置里还为此写死了 `RAG_MAX_UPLOAD_CHUNKS=200` 这种上限。

现在端点只做「校验 → 落盘 → 建 pending 行 → 投递」并立刻返回，
真正的活在这里干。前端本来就是按列表 3 秒轮询的
（KnowledgeBase.vue 的 schedulePoll），所以待处理 → 处理中 → 就绪的
状态流转天然可见，不需要新增接口。
"""
import time

from tasks.celery_app import celery_app
from tasks.context import app_context


@celery_app.task(name='knowledge.ingest', bind=True)
def ingest_document(self, doc_id, username=None, force=False):
    """把 doc_id 对应的文档切片入库

    `username` 只用于审计日志：worker 里没有请求上下文，
    `log_operation` 会退回记 `system`，把上传者一并投递过来才能保住审计链。

    `force=True` 用于「重新入库」：内容可能没变，但要推倒重来。
    """
    started = time.time()

    with app_context():
        from core.helpers import log_operation
        from database import KnowledgeDoc, db
        from services.rag.pipeline import RAGPipeline
        from utils.logger import logger

        doc = db.session.get(KnowledgeDoc, doc_id)
        if doc is None:
            logger.warning('入库任务的目标文档不存在（可能已被删除）: doc_id=%s', doc_id)
            return {'doc_id': doc_id, 'status': 'missing'}

        title = doc.title

        result = RAGPipeline().ingest_doc_row(doc_id, force=force)

        # 审计写在 worker 里：写在端点里的话，时点会停在"已提交"而非真实结果
        if result.status == 'failed':
            log_operation(f'知识库入库失败: {title}', False, result.error,
                          username=username)
        elif result.skipped:
            # 内容未变而跳过，不算一次失败，但也不该伪装成"入库成功"
            logger.info('知识库入库跳过（内容未变）: %s', title)
        else:
            log_operation(f'知识库入库: {title} → {result.chunks} 切片',
                          username=username)

        logger.info('知识库任务结束: doc_id=%s status=%s 耗时 %.1fs',
                    doc_id, result.status, time.time() - started)
        return {
            'doc_id': result.doc_id,
            'status': result.status,
            'chunks': result.chunks,
            'error': result.error,
            'elapsed': round(result.elapsed, 2),
        }


@celery_app.task(name='knowledge.ingest_patient', bind=True)
def ingest_patient_records_task(self, patient_id, username=None):
    """把某患者的病历与检测报告重新切片入库（阶段 12 补的钩子）

    ## 为什么需要它

    在此之前，`ingest_patient_records` **只有 `scripts/ingest_knowledge.py`
    一个调用点** —— 医生改了病历或新出报告之后，知识库里的个人切片还是旧的，
    患者问"我上次诊断出什么问题"会得到基于过期病历的回答；病历删了，那条
    派生文档也一直留在索引里。阶段 7 的语料管线早就支持按 `updated_at` 重算，
    只是**没人触发它**（方案里这条被标成"可选、可裁剪"，然后就一直没做）。

    ## 为什么走队列而不是在请求里同步做

    切片要跑嵌入模型（GPU，几十秒），放在保存病历的请求里会把医生页面卡住。
    走队列则请求立即返回，切片在后台完成——与文档上传的异步化是同一个取舍
    （见本模块开头的说明）。

    投递失败**不影响业务**：病历已经存好了，只是知识库暂时陈旧 ——
    调用方（api/doctor.py）只记 WARNING，不把异常抛给医生。
    """
    started = time.time()
    with app_context():
        from core.helpers import log_operation
        from services.rag.pipeline import RAGPipeline
        from utils.logger import logger

        stats = RAGPipeline().reingest_patient_records(patient_id)
        logger.info('患者记录入库结束: patient_id=%s 入库 %s 篇 / 清理过期 %s 篇，'
                    '耗时 %.1fs', patient_id, stats['ingested'], stats['pruned'],
                    time.time() - started)
        log_operation(
            f'患者记录重新切片: patient_id={patient_id} '
            f'入库 {stats["ingested"]} 篇、清理过期 {stats["pruned"]} 篇',
            username=username)
        stats['patient_id'] = patient_id
        stats['elapsed'] = round(time.time() - started, 2)
        return stats
