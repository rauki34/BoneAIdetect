"""知识库管理接口

面向医护人员的文档管理：上传即入库、可检索预览、可重新入库、可删除。
路由保留完整路径（不使用 url_prefix），与其余蓝图一致。

权限口径：
- 共享知识库是**机构数据**：医生可上传、可查看，但只有管理员能删除
- 患者个人资料：需通过医患关联校验，医生只能操作自己关联的患者
"""
import hashlib
import json
import mimetypes
import os
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

from core.auth import get_current_user, require_role
from core.helpers import can_access_patient, log_operation
from core.paths import KNOWLEDGE_UPLOAD_DIR
from core.ratelimit import limit
from database import KnowledgeChunk, KnowledgeDoc, safe_json_loads, db
from services.rag.loader import SUPPORTED_EXTENSIONS, ScannedPdfError
from services.rag.pipeline import RAGPipeline
from services.rag.retriever import (
    RetrievalScope, get_retriever, shared_scope,
)
from utils.logger import logger

bp = Blueprint('knowledge', __name__)

ALLOWED_EXTENSIONS = set(SUPPORTED_EXTENSIONS)


def _max_upload_bytes():
    from flask import current_app
    return int(current_app.config.get('RAG_MAX_UPLOAD_MB', 50)) * 1024 * 1024


def _upload_dir():
    """按年月分目录，避免单目录堆积"""
    sub = os.path.join(KNOWLEDGE_UPLOAD_DIR, datetime.now().strftime('%Y'),
                       datetime.now().strftime('%m'))
    os.makedirs(sub, exist_ok=True)
    return sub


def _storage_name(filename):
    """生成落盘文件名

    **不能用 werkzeug.secure_filename**：它会把非 ASCII 字符全部剥掉，
    `骨折指南.pdf` 会变成 `pdf` 甚至空串——中文语料会丢文件名并互相覆盖。
    原始文件名另存在 doc_meta 里仅供展示。
    """
    suffix = os.path.splitext(filename or '')[1].lower()
    return f'{uuid.uuid4().hex}{suffix}'


@bp.route("/api/knowledge/docs", methods=["GET"])
@require_role('doctor', 'admin')
def list_docs():
    """文档列表

    医生默认只看共享库；传 patient_id 时需通过医患关联校验。
    """
    user = get_current_user()
    query = KnowledgeDoc.query
    patient_id = request.args.get('patient_id')
    if patient_id:
        if not can_access_patient(user, patient_id):
            return jsonify({"success": False, "error": "无权访问该患者的资料"}), 403
        query = query.filter(KnowledgeDoc.patient_id == int(patient_id))
    else:
        query = query.filter(KnowledgeDoc.patient_id.is_(None))

    status = request.args.get('status')
    if status:
        query = query.filter(KnowledgeDoc.status == status)

    keyword = (request.args.get('keyword') or '').strip()
    if keyword:
        query = query.filter(KnowledgeDoc.title.ilike(f'%{keyword}%'))

    docs = query.order_by(KnowledgeDoc.created_at.desc()).limit(200).all()
    return jsonify({"success": True, "data": [d.to_dict() for d in docs]})


@bp.route("/api/knowledge/docs/<int:doc_id>", methods=["GET"])
@require_role('doctor', 'admin')
def doc_detail(doc_id):
    user = get_current_user()
    doc = db.session.get(KnowledgeDoc, doc_id)
    if not doc:
        return jsonify({"success": False, "error": "文档不存在"}), 404
    if doc.patient_id is not None and not can_access_patient(user, doc.patient_id):
        return jsonify({"success": False, "error": "无权访问该文档"}), 403
    data = doc.to_dict()
    data['chunks'] = [c.to_dict() for c in
                      doc.chunks.order_by(KnowledgeChunk.chunk_index).limit(200)]
    return jsonify({"success": True, "data": data})


@bp.route("/api/knowledge/docs/<int:doc_id>/chunks", methods=["GET"])
@require_role('doctor', 'admin')
def doc_chunks(doc_id):
    user = get_current_user()
    doc = db.session.get(KnowledgeDoc, doc_id)
    if not doc:
        return jsonify({"success": False, "error": "文档不存在"}), 404
    if doc.patient_id is not None and not can_access_patient(user, doc.patient_id):
        return jsonify({"success": False, "error": "无权访问该文档"}), 403
    limit_n = min(int(request.args.get('limit', 200)), 500)
    chunks = (doc.chunks.order_by(KnowledgeChunk.chunk_index).limit(limit_n).all())
    # status 一并返回：文档在 processing 时 chunks 为空，与"真的零切片"无法区分
    return jsonify({"success": True, "status": doc.status,
                    "data": [c.to_dict() for c in chunks]})


def _enqueue_ingest(doc, username, force=False):
    """把入库任务投进队列；成功返回 None，失败返回可直接 return 的响应

    broker 不可用时**必须清掉刚建的那一行**：留下一行永远 pending 的文档，
    前端会盯着它无限轮询，而队列里根本没有对应任务。
    回报 503 让人知道是暂时性故障，而不是 500 让人以为代码坏了。

    回滚由调用方做：上传时该删掉刚建的行，重新入库时该只还原状态。
    """
    from tasks.knowledge import ingest_document
    try:
        ingest_document.delay(doc.id, username=username, force=force)
    except Exception as e:
        logger.error('投递入库任务失败(doc_id=%s): %s', doc.id, e, exc_info=True)
        db.session.rollback()
        return ("任务队列不可用，文档未入库。请确认 Redis 与 Celery worker 已启动"
                "（bash scripts/redis.sh start && bash scripts/celery.sh start）")
    return None


@bp.route("/api/knowledge/docs", methods=["POST"])
@limit('kb_upload', key='user')
@require_role('doctor', 'admin')
def upload_doc():
    """上传文档并**异步入库**

    端点只做校验、落盘、建 pending 行、投递任务，然后立刻返回 doc_id。
    切片与向量化在 Celery worker 里跑，文档状态经 pending → processing →
    ready/failed，前端按 3 秒轮询刷新。

    这样做的收益不只是"请求变快"：解析失败（扫描件等）以前必须在 HTTP
    响应里同步返回 422，现在变成文档置 failed 并把原因写进 error_msg，
    失败详情在管理界面上直接可见，且上传不再被解析耗时卡住。

    不再返回 chunks（此刻还没有切片），改为返回 status='pending'。
    """
    from flask import current_app

    user = get_current_user()
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "未选择文件"}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({"success": False, "error": "文件名为空"}), 400

    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": f'不支持的文件类型 {suffix}，仅支持 '
                     + '、'.join(sorted(ALLOWED_EXTENSIONS)),
        }), 415

    raw = file.read()
    if len(raw) > _max_upload_bytes():
        return jsonify({
            "success": False,
            "error": f'文件超过 {current_app.config.get("RAG_MAX_UPLOAD_MB", 50)}MB 上限',
        }), 413
    if not raw:
        return jsonify({"success": False, "error": "文件内容为空"}), 400

    origin = (request.form.get('origin') or 'curated').strip()
    source = (request.form.get('source') or '').strip()
    # 「公开原文」必须能指出出处：标着"这是公开资料原文"却给不出来源，
    # 等于让系统替一份无法核实的材料背书。宁可让上传者补一行出处。
    if origin == 'public' and not source:
        return jsonify({
            "success": False,
            "error": "标注为「公开原文」时必须填写出处（文献引用或链接），"
                     "否则请改选「整理摘要」",
        }), 400

    patient_id = request.form.get('patient_id')
    if patient_id:
        if not can_access_patient(user, patient_id):
            return jsonify({"success": False, "error": "无权为该患者上传资料"}), 403
        patient_id = int(patient_id)

    original_name = file.filename
    path = os.path.join(_upload_dir(), _storage_name(original_name))
    with open(path, 'wb') as fh:
        fh.write(raw)

    file_hash = hashlib.sha256(raw).hexdigest()
    title = request.form.get('title') or Path(original_name).stem

    # 去重必须在建行之前做，否则会留下一条永远不会被处理的 pending 行：
    # 入库任务走到 ingest_doc_row 时会发现内容未变而跳过，那一行就没人管了，
    # 前端还会一直轮询它。CLI 与 verify 脚本重跑时必然触发这条路径。
    existing = RAGPipeline._find_existing(file_hash, patient_id, path)
    if existing is not None and existing.file_hash == file_hash:
        return jsonify({
            "success": True,
            "doc_id": existing.id,
            "title": existing.title,
            "status": existing.status,
            "skipped": True,
            "reason": '内容未变，已存在',
        })

    doc = KnowledgeDoc(
        title=title,
        doc_type=request.form.get('doc_type') or 'other',
        department=request.form.get('department') or None,
        source=source or '',
        origin=origin,
        file_path=path,
        file_hash=file_hash,
        file_size=len(raw),
        mime_type=mimetypes.guess_type(original_name)[0] or 'application/octet-stream',
        patient_id=patient_id,
        uploaded_by=user.id,
        status='pending',
        doc_meta=json.dumps({'original_filename': original_name}, ensure_ascii=False),
    )
    db.session.add(doc)
    db.session.commit()

    err = _enqueue_ingest(doc, username=user.username)
    if err is not None:
        # 删掉刚建的行：留下它前端会盯着一条永远不会被处理的 pending 文档
        db.session.delete(doc)
        db.session.commit()
        return jsonify({"success": False, "error": err}), 503

    # 审计留在这里（"谁提交了什么"），入库结果的那条由 worker 补
    log_operation(f'知识库上传已受理: {title}（待入库）')
    return jsonify({
        "success": True,
        "doc_id": doc.id,
        "title": doc.title,
        "status": doc.status,
    }), 202


@bp.route("/api/knowledge/docs/<int:doc_id>", methods=["DELETE"])
@require_role('doctor', 'admin')
def delete_doc(doc_id):
    """删除文档

    共享库是机构数据：医生可上传但**不可删除**，只有管理员能删。
    自己的上传若是患者资料，按归属校验。
    """
    user = get_current_user()
    doc = db.session.get(KnowledgeDoc, doc_id)
    if not doc:
        return jsonify({"success": False, "error": "文档不存在"}), 404

    if doc.patient_id is None:
        if user.role != 'admin':
            return jsonify({
                "success": False,
                "error": "共享知识库为机构数据，仅管理员可删除",
            }), 403
    elif not can_access_patient(user, doc.patient_id):
        return jsonify({"success": False, "error": "无权删除该文档"}), 403

    # 正在入库的文档不能删：worker 拿着 doc_id 往这一行里写切片，
    # 行没了它会继续往一个已删除的 doc_id 写，留下无人认领的切片。
    # 入库是分钟级的事，让使用者稍后重试即可。
    if doc.status == 'processing':
        return jsonify({
            "success": False,
            "error": "文档正在入库中，请等状态变为「就绪」或「失败」后再删除",
        }), 409

    title = doc.title
    # 只删上传落盘的文件；语料目录里的文件随仓库管理，不在此处删
    if doc.file_path and os.path.abspath(doc.file_path).startswith(
            os.path.abspath(KNOWLEDGE_UPLOAD_DIR)) and os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except OSError as e:
            logger.warning('删除知识库文件失败（记录继续删除）: %s', e)

    db.session.delete(doc)
    db.session.commit()
    from services.rag import store
    store.invalidate_cache()
    log_operation(f'删除知识库文档: {title}')
    return jsonify({"success": True})


@bp.route("/api/knowledge/docs/<int:doc_id>/reingest", methods=["POST"])
@limit('kb_upload', key='user')
@require_role('admin')
def reingest_doc(doc_id):
    """重新入库（切片策略调整、或上次失败后重试）

    走 `ingest_doc_row` 而不是 `ingest_file`：后者会 delete 旧行再建新行，
    **doc_id 会变**。前端「重试」按钮就长在这一行上，行没了它会在列表里
    突然消失又出现；verify 脚本按 doc_id 做的清理也会失败。
    """
    doc = db.session.get(KnowledgeDoc, doc_id)
    if not doc:
        return jsonify({"success": False, "error": "文档不存在"}), 404
    if not doc.file_path or not os.path.exists(doc.file_path):
        return jsonify({
            "success": False,
            "error": "该文档没有可用的原始文件（可能是由病历派生的记录）",
        }), 400
    if doc.status == 'processing':
        return jsonify({
            "success": False,
            "error": "文档正在入库中，无需重复提交",
        }), 409

    # 先置 pending 让前端立刻进入轮询；投递失败再还原，别让 UI 停在"排队中"
    prev_status = doc.status
    doc.status = 'pending'
    db.session.commit()

    # force=True：内容多半没变，但重新入库的本意就是推倒重来
    err = _enqueue_ingest(doc, username=get_current_user().username, force=True)
    if err is not None:
        doc = db.session.get(KnowledgeDoc, doc_id)
        if doc is not None:
            doc.status = prev_status
            db.session.commit()
        return jsonify({"success": False, "error": err}), 503

    log_operation(f'知识库重新入库已受理: {doc.title}')
    return jsonify({
        "success": True,
        "doc_id": doc.id,
        "title": doc.title,
        "status": doc.status,
    }), 202


@bp.route("/api/knowledge/search", methods=["POST"])
@limit('kb_search', key='user')
@require_role('doctor', 'admin')
def search():
    """检索预览

    响应里带上 vec_rank / bm25_rank / rrf_score，让混合检索可被观察：
    能直观看到向量头名与 BM25 头名不同、RRF 如何调和、重排如何定序。
    """
    user = get_current_user()
    data = request.get_json() or {}
    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({"success": False, "error": "查询内容不能为空"}), 400

    patient_id = data.get('patient_id')
    include_personal = False
    if patient_id and data.get('include_personal'):
        if not can_access_patient(user, patient_id):
            return jsonify({"success": False, "error": "无权检索该患者的病历"}), 403
        include_personal = True

    scope = RetrievalScope(
        patient_id=int(patient_id) if include_personal else None,
        include_personal=include_personal,
    ) if include_personal else shared_scope()

    top_k = min(int(data.get('top_k', 5)), 20)
    doc_types = data.get('doc_types') or None

    import time
    started = time.time()
    chunks = get_retriever().retrieve_safely(
        query, scope=scope, top_k=top_k, doc_types=doc_types)
    took_ms = int((time.time() - started) * 1000)

    return jsonify({
        "success": True,
        "query": query,
        "scope": {
            "patient_id": scope.patient_id,
            "include_shared": scope.include_shared,
            "include_personal": scope.include_personal,
        },
        "rerank_used": bool(chunks and chunks[0].rerank_used),
        "took_ms": took_ms,
        "results": [c.to_dict() for c in chunks],
    })


@bp.route("/api/knowledge/stats", methods=["GET"])
@require_role('doctor', 'admin')
def stats():
    """知识库概览"""
    user = get_current_user()
    shared = KnowledgeDoc.query.filter(KnowledgeDoc.patient_id.is_(None))
    by_origin = {}
    by_type = {}
    for origin, count in db.session.query(
            KnowledgeDoc.origin, db.func.count(KnowledgeDoc.id)
    ).filter(KnowledgeDoc.patient_id.is_(None)).group_by(KnowledgeDoc.origin):
        by_origin[origin or 'unknown'] = count
    for doc_type, count in db.session.query(
            KnowledgeDoc.doc_type, db.func.count(KnowledgeDoc.id)
    ).filter(KnowledgeDoc.patient_id.is_(None)).group_by(KnowledgeDoc.doc_type):
        by_type[doc_type or 'other'] = count

    from services.rag.embedder import Embedder
    from services.rag.reranker import Reranker
    embedder = Embedder.instance()

    return jsonify({
        "success": True,
        "data": {
            "docs_shared": shared.count(),
            "docs_ready": shared.filter(KnowledgeDoc.status == 'ready').count(),
            "docs_failed": shared.filter(KnowledgeDoc.status == 'failed').count(),
            "chunks": KnowledgeChunk.query.filter(
                KnowledgeChunk.patient_id.is_(None)).count(),
            "chunks_personal": KnowledgeChunk.query.filter(
                KnowledgeChunk.patient_id.isnot(None)).count(),
            "by_origin": by_origin,
            "by_type": by_type,
            "embedder_ready": embedder.available,
            "reranker_configured": bool(Reranker.instance()),
            "role": user.role,
        },
    })
