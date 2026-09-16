"""知识库管理接口

面向医护人员的文档管理：上传即入库、可检索预览、可重新入库、可删除。
路由保留完整路径（不使用 url_prefix），与其余蓝图一致。

权限口径：
- 共享知识库是**机构数据**：医生可上传、可查看，但只有管理员能删除
- 患者个人资料：需通过医患关联校验，医生只能操作自己关联的患者
"""
import json
import os
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request

from core.auth import get_current_user, require_role
from core.helpers import can_access_patient, log_operation
from core.paths import KNOWLEDGE_UPLOAD_DIR
from core.ratelimit import limit
from database import KnowledgeChunk, KnowledgeDoc, safe_json_loads, db
from services.rag.loader import SUPPORTED_EXTENSIONS, ScannedPdfError
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
    return jsonify({"success": True, "data": [c.to_dict() for c in chunks]})


@bp.route("/api/knowledge/docs", methods=["POST"])
@limit('kb_upload', key='user')
@require_role('doctor', 'admin')
def upload_doc():
    """上传文档并同步入库

    同步执行（Celery 是后续阶段的事）。因此对页数与切片数设上限：
    入库耗时必须留在前端与代理的超时之内，超出部分引导走命令行脚本。
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

    patient_id = request.form.get('patient_id')
    if patient_id:
        if not can_access_patient(user, patient_id):
            return jsonify({"success": False, "error": "无权为该患者上传资料"}), 403
        patient_id = int(patient_id)

    path = os.path.join(_upload_dir(), _storage_name(file.filename))
    with open(path, 'wb') as fh:
        fh.write(raw)

    from services.rag.pipeline import RAGPipeline
    result = RAGPipeline().ingest_file(
        path,
        title=request.form.get('title') or None,
        doc_type=request.form.get('doc_type') or None,
        department=request.form.get('department') or None,
        source=request.form.get('source') or None,
        origin=request.form.get('origin') or None,
        patient_id=patient_id,
        uploaded_by=user.id,
        apply=True,
    )

    if result.status == 'failed':
        log_operation(f'知识库上传失败: {file.filename}', False, result.error)
        # 扫描件属于"用户可自行纠正"的失败，用 422 与明确文案区分于服务端错误
        code = 422 if '无文本层' in (result.error or '') else 500
        return jsonify({
            "success": False,
            "error": result.error or '入库失败',
            "doc_id": result.doc_id,
        }), code

    # 同步入库的规模上限：超出部分在响应里明确告知，引导走脚本
    max_chunks = int(current_app.config.get('RAG_MAX_UPLOAD_CHUNKS', 200))
    warning = None
    if result.chunks > max_chunks:
        warning = (f'本次入库 {result.chunks} 个切片，超过建议上限 {max_chunks}；'
                   f'大批量资料建议使用 scripts/ingest_knowledge.py')

    log_operation(f'知识库上传: {result.title} → {result.chunks} 切片')
    return jsonify({
        "success": True,
        "doc_id": result.doc_id,
        "title": result.title,
        "chunks": result.chunks,
        "status": result.status,
        "warning": warning,
    })


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
    """重新入库（切片策略调整、或上次失败后重试）"""
    doc = db.session.get(KnowledgeDoc, doc_id)
    if not doc:
        return jsonify({"success": False, "error": "文档不存在"}), 404
    if not doc.file_path or not os.path.exists(doc.file_path):
        return jsonify({
            "success": False,
            "error": "该文档没有可用的原始文件（可能是由病历派生的记录）",
        }), 400

    from services.rag.pipeline import RAGPipeline
    result = RAGPipeline().ingest_file(
        doc.file_path, title=doc.title, doc_type=doc.doc_type,
        department=doc.department, source=doc.source, origin=doc.origin,
        patient_id=doc.patient_id, uploaded_by=doc.uploaded_by,
        apply=True, replace=True,
    )
    if result.status == 'failed':
        log_operation(f'知识库重新入库失败: {doc.title}', False, result.error)
        return jsonify({"success": False, "error": result.error}), 500
    log_operation(f'知识库重新入库: {result.title} → {result.chunks} 切片')
    return jsonify({"success": True, "chunks": result.chunks})


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
