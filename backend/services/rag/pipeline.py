"""入库编排：解析 → 切片 → 向量化 → 落库

事务边界是这里最需要小心的地方，三条规则：

1. **先落 processing 状态再向量化**。文档行先提交，拿到 id，管理界面立刻可见；
   中途崩溃留下一条可见的 processing 行（启动时由 store.recover_stale_docs 回收），
   而不是上传静默丢失。
2. **向量化在任何事务之外做**。一份 200 切片的文档要跑约 30 秒，把 PG 事务
   横跨这段时间会长时间占用连接池连接、撑大 WAL。
3. **不变量：切片存在 ⟺ 文档是 ready**。失败时删掉该文档已有切片并置 failed，
   宁可丢掉已算好的批次，也不留下半入库的文档——检索侧就不必处理"部分可用"
   这种状态。
"""
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.paths import KNOWLEDGE_CORPUS_DIR
from database import KnowledgeChunk, KnowledgeDoc, db, safe_json_loads
from services.rag import store
from services.rag.embedder import Embedder
from services.rag.loader import (
    ORIGIN_PATIENT_RECORD, LoadError, load_document, load_text_document,
)
from services.rag.splitter import MedicalSplitter
from utils.logger import logger

BATCH_COMMIT_SIZE = 64      # 每多少切片提交一次（与嵌入批大小无关）


@dataclass
class IngestResult:
    title: str = ''
    path: str = ''
    doc_id: int | None = None
    status: str = 'pending'
    chunks: int = 0
    skipped: bool = False
    reason: str = ''
    elapsed: float = 0.0
    error: str = ''
    warnings: list = field(default_factory=list)

    @property
    def ok(self):
        return self.status == 'ready'


class RAGPipeline:
    """入库编排 + （阶段 7-2 起）检索入口"""

    def __init__(self, splitter=None, embedder=None):
        self.splitter = splitter or MedicalSplitter()
        self.embedder = embedder or Embedder.instance()

    # ---------- 去重 ----------

    @staticmethod
    def _scope_filter(query, patient_id):
        """限定归属

        共享库的判定必须是 `.is_(None)`：SQL 里 `= NULL` 恒为假，
        写成 `== None` 会让共享语料每次运行都被判为"新文档"而全量重入库。
        """
        if patient_id is None:
            return query.filter(KnowledgeDoc.patient_id.is_(None))
        return query.filter(KnowledgeDoc.patient_id == patient_id)

    @classmethod
    def _find_existing(cls, file_hash, patient_id, file_path=None):
        """查已入库的文档：先按**路径**，再按内容哈希

        按路径优先很重要：内容哈希只能识别"同一份内容"，
        改了错别字就变成新哈希。若只按哈希去重，编辑过的语料文件会被当成
        新文档入库，旧版本继续留在索引里参与检索——使用者看到的是已修正
        之前的内容，且无从察觉。同一路径视为同一文档的更新。
        """
        if file_path:
            same_path = cls._scope_filter(
                KnowledgeDoc.query.filter_by(file_path=str(file_path)), patient_id,
            ).first()
            if same_path is not None:
                return same_path
        return cls._scope_filter(
            KnowledgeDoc.query.filter_by(file_hash=file_hash), patient_id,
        ).first()

    # ---------- 入库主流程 ----------

    def ingest_file(self, path, *, doc_type=None, department=None, source=None,
                    origin=None, patient_id=None, uploaded_by=None, title=None,
                    apply=True, replace=False, batch_size=None):
        path = Path(path)
        started = time.time()
        try:
            loaded = load_document(path)
        except LoadError as e:
            # 扫描件等解析失败：留下 failed 记录，让使用者看到原因
            return self._record_failure(
                str(path), title or path.stem, str(e), patient_id, uploaded_by,
                apply, path_obj=path)

        raw = path.read_bytes()
        file_hash = hashlib.sha256(raw).hexdigest()
        meta = loaded.meta
        return self._ingest(
            loaded, file_hash=file_hash, file_path=str(path), title=title,
            doc_type=doc_type or meta.get('doc_type'),
            department=department or meta.get('department'),
            source=source if source is not None else meta.get('source'),
            origin=origin or meta.get('origin'),
            patient_id=patient_id, uploaded_by=uploaded_by,
            apply=apply, replace=replace, batch_size=batch_size,
            file_size=len(raw), mime_type=_mime_of(path),
            original_filename=path.name, started=started,
            doc_meta_extra=_extra_meta(meta),
        )

    def ingest_text(self, text, *, title, file_hash, doc_type='record',
                    department=None, source='', origin=ORIGIN_PATIENT_RECORD,
                    patient_id=None, uploaded_by=None, apply=True,
                    replace=False, batch_size=None, doc_meta_extra=None):
        started = time.time()
        loaded = load_text_document(text, title=title, meta={
            'doc_type': doc_type,
            'department': department or '骨科',
            'origin': origin,
            'source': source,
        })
        return self._ingest(
            loaded, file_hash=file_hash, file_path=None, title=title,
            doc_type=doc_type, department=department, source=source,
            origin=origin, patient_id=patient_id, uploaded_by=uploaded_by,
            apply=apply, replace=replace, batch_size=batch_size,
            file_size=len(text.encode('utf-8')), mime_type='text/plain',
            original_filename=None, started=started,
            doc_meta_extra=doc_meta_extra,
        )

    def _ingest(self, loaded, *, file_hash, file_path, title, doc_type,
                department, source, origin, patient_id, uploaded_by, apply,
                replace, batch_size, file_size, mime_type, original_filename,
                started, doc_meta_extra=None):
        title = title or loaded.title
        existing = self._find_existing(file_hash, patient_id, file_path)
        # 同路径但内容变了 = 语料被编辑过，按"更新"处理而非"已存在"
        updated = existing is not None and existing.file_hash != file_hash

        if not apply:
            chunks = self.splitter.split(loaded)
            return IngestResult(
                title=title, path=file_path or '', status='dry-run',
                chunks=len(chunks), skipped=existing is not None,
                reason='已入库（内容未变）' if existing else '待入库',
                elapsed=time.time() - started, warnings=loaded.warnings,
            )

        if existing and not replace and not updated:
            return IngestResult(
                title=existing.title, path=file_path or '', doc_id=existing.id,
                status=existing.status, chunks=existing.chunk_count,
                skipped=True, reason='内容未变，跳过',
                elapsed=time.time() - started,
            )

        if existing:            # --replace 或内容已更新：整篇重建
            db.session.delete(existing)
            db.session.commit()

        doc = KnowledgeDoc(
            title=title, doc_type=doc_type or 'other', department=department,
            source=source or '', origin=origin or 'curated',
            language=loaded.meta.get('language', 'zh'),
            file_path=file_path, file_hash=file_hash, file_size=file_size,
            mime_type=mime_type, patient_id=patient_id, uploaded_by=uploaded_by,
            status='processing', char_count=loaded.char_count,
            doc_meta=_dump_meta(doc_meta_extra, original_filename),
        )
        db.session.add(doc)
        db.session.commit()

        try:
            chunks = self.splitter.split(loaded)
            if not chunks:
                raise ValueError('切片结果为空，文档可能没有可索引的正文')
            self._embed_and_store(doc, chunks, batch_size)

            doc.status = 'ready'
            doc.chunk_count = len(chunks)
            doc.error_msg = None
            db.session.commit()
            store.invalidate_cache()
            logger.info('知识库入库完成: %s → %d 切片 (%.1fs)',
                        title, len(chunks), time.time() - started)
            return IngestResult(
                title=title, path=file_path or '', doc_id=doc.id,
                status='ready', chunks=len(chunks),
                elapsed=time.time() - started, warnings=loaded.warnings,
            )
        except Exception as e:
            db.session.rollback()
            self._cleanup_failed(doc, e)
            logger.error('知识库入库失败: %s - %s', title, e, exc_info=True)
            return IngestResult(
                title=title, path=file_path or '', doc_id=doc.id,
                status='failed', error=str(e),
                elapsed=time.time() - started,
            )

    def _embed_and_store(self, doc, chunks, batch_size):
        """分批向量化并写库

        向量化本身不在事务里：`encode_documents` 是纯 GPU 计算，
        提交按 BATCH_COMMIT_SIZE 分批另做。
        """
        pending = []
        for i in range(0, len(chunks), self._embed_step(batch_size)):
            window = chunks[i:i + self._embed_step(batch_size)]
            vectors = self.embedder.encode_documents(
                [c.content for c in window], batch_size=batch_size,
            )
            for chunk, vector in zip(window, vectors):
                pending.append(KnowledgeChunk(
                    doc_id=doc.id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    section=chunk.section or None,
                    page=chunk.page,
                    patient_id=doc.patient_id,     # 反规范化，隔离过滤靠它
                    embedding=vector,
                ))
                if len(pending) >= BATCH_COMMIT_SIZE:
                    db.session.bulk_save_objects(pending)
                    db.session.commit()
                    pending = []
        if pending:
            db.session.bulk_save_objects(pending)
            db.session.commit()

    @staticmethod
    def _embed_step(batch_size):
        batch_size = batch_size or 8
        # 一次交给编码器的条数；大于提交粒度时按提交粒度走，避免一次攒太多
        return max(batch_size, BATCH_COMMIT_SIZE)

    def _cleanup_failed(self, doc, error):
        """违反不变量时回滚：删掉该文档的所有切片，置 failed"""
        try:
            KnowledgeChunk.query.filter_by(doc_id=doc.id).delete(
                synchronize_session=False)
            doc.status = 'failed'
            doc.error_msg = str(error)[:1000]
            doc.chunk_count = 0
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error('清理失败入库文档 %s 时出错: %s', doc.id, e)

    def _record_failure(self, path, title, error, patient_id, uploaded_by,
                        apply, path_obj=None):
        """解析阶段就失败的文档（扫描件、损坏文件）也要留痕"""
        if not apply:
            return IngestResult(title=title, path=path, status='dry-run',
                                reason=f'解析失败: {error}', error=error)
        doc = KnowledgeDoc(
            title=title, doc_type='other', origin='curated', source='',
            file_path=path, status='failed', error_msg=error[:1000],
            patient_id=patient_id, uploaded_by=uploaded_by,
            file_size=path_obj.stat().st_size if path_obj and path_obj.exists() else None,
        )
        db.session.add(doc)
        db.session.commit()
        store.invalidate_cache()
        logger.warning('知识库文档解析失败: %s - %s', title, error)
        return IngestResult(title=title, path=path, doc_id=doc.id,
                            status='failed', error=error)

    # ---------- 批量入口 ----------

    def ingest_corpus(self, corpus_dir=None, *, apply=True, replace=False,
                      batch_size=None, only=None):
        """入库知识库语料目录

        `only` 可传单个文件路径，用于只处理一个文件。
        """
        corpus_dir = Path(corpus_dir or KNOWLEDGE_CORPUS_DIR)
        if not corpus_dir.exists():
            logger.warning('语料目录不存在: %s', corpus_dir)
            return []

        if only:
            files = [Path(only)]
        else:
            files = sorted(
                p for p in corpus_dir.rglob('*')
                if p.is_file() and not p.name.startswith('.')
                and p.suffix.lower() in ('.md', '.markdown', '.txt', '.pdf', '.docx')
            )

        results = []
        for path in files:
            relative = path.relative_to(corpus_dir) if corpus_dir in path.parents \
                else Path(path.name)
            # 一级子目录名作为 doc_type 兜底（corpus/guideline/xxx.md）
            fallback_type = relative.parts[0] if len(relative.parts) > 1 else None
            loaded_type = None
            try:
                from services.rag.loader import load_document
                loaded_type = load_document(path).meta.get('doc_type')
            except LoadError:
                pass
            results.append(self.ingest_file(
                path, doc_type=loaded_type or fallback_type,
                apply=apply, replace=replace, batch_size=batch_size,
            ))
        return results

    def ingest_patient_records(self, patient_id=None, *, apply=True,
                               replace=False, batch_size=None):
        """把患者本人的病历/检测报告切片入库

        这些内容只应被该患者自己的检索命中，因此 patient_id 必须落库，
        由 RetrievalScope 强制过滤（见 retriever.py）。
        """
        from database import DetectionHistory, MedicalRecord, User

        patients = []
        if patient_id:
            user = db.session.get(User, patient_id)
            if user:
                patients.append(user)
        else:
            role_filter = User.role == 'patient'
            patients = User.query.filter(role_filter).all()

        results = []
        for user in patients:
            records = MedicalRecord.query.filter_by(
                patient_id=user.id).order_by(MedicalRecord.visit_date.desc()).all()
            for record in records:
                text = _medical_record_text(record)
                results.append(self.ingest_text(
                    text,
                    title=f'病历 {record.record_number or record.id}',
                    file_hash=_text_hash(f'medical_record:{record.id}:'
                                         f'{record.updated_at}'),
                    doc_type='record', patient_id=user.id,
                    # 出处不能留空：引用卡片会显示一个空来源。
                    # 患者病历的出处就是本院病历系统本身。
                    source='本院电子病历系统（患者本人记录）',
                    apply=apply, replace=replace, batch_size=batch_size,
                    doc_meta_extra={'source_table': 'medical_records',
                                    'source_id': record.id},
                ))

            reports = DetectionHistory.query.filter_by(
                patient_id=user.id).order_by(DetectionHistory.timestamp.desc()).all()
            for report in reports:
                text = _detection_report_text(report)
                results.append(self.ingest_text(
                    text,
                    title=f'检测报告 {report.id}',
                    file_hash=_text_hash(f'detection_history:{report.id}:'
                                         f'{report.timestamp}'),
                    doc_type='record', patient_id=user.id,
                    source='本院骨折检测报告（患者本人记录）',
                    apply=apply, replace=replace, batch_size=batch_size,
                    doc_meta_extra={'source_table': 'detection_history',
                                    'source_id': report.id},
                ))
        return results

    def prune_corpus(self, corpus_dir=None):
        """删除语料目录中已不存在的文件的库内记录（共享库）"""
        corpus_dir = Path(corpus_dir or KNOWLEDGE_CORPUS_DIR)
        removed = 0
        docs = KnowledgeDoc.query.filter(
            KnowledgeDoc.patient_id.is_(None),
            KnowledgeDoc.file_path.isnot(None),
        ).all()
        for doc in docs:
            if not Path(doc.file_path).exists():
                logger.info('清理已删除的语料记录: %s', doc.title)
                db.session.delete(doc)
                removed += 1
        if removed:
            db.session.commit()
            store.invalidate_cache()
        return removed


def _detection_report_text(report):
    """把一份检测报告渲染成可检索的文本

    **只收临床事实，不收既往的 AI 解读**（`medical_advice.interpretation` 等）。

    原因：把 AI 生成的分析文本也当作"病历"入库，会形成
        AI 解读 → 存进病历 → 切片入库 → 被检索为参考资料 → 下一代解读再引用它
    的回路。后果有两个：一是引用卡片标着「本人病历」，
    内容却是 AI 写的，患者会误以为是医生结论；二是上一轮的错误会被
    当成"事实"逐轮强化。
    解读文本在界面上照常看得到，只是不再充当知识源。
    """
    detections = safe_json_loads(report.detections, []) or []

    lines = [
        f'检查日期：{report.timestamp.strftime("%Y-%m-%d") if report.timestamp else "未知"}',
        f'影像文件：{report.filename}',
        f'使用模型：{report.model}',
    ]
    if detections:
        findings = []
        for det in detections:
            name = det.get('class') or det.get('label') or '未知'
            conf = det.get('confidence')
            findings.append(f'{name}（置信度 {conf:.2f}）' if isinstance(conf, (int, float))
                            else str(name))
        lines.append('检出结果：' + '、'.join(findings) + f'，共 {report.count} 处')
    if report.diagnosis:
        lines.append(f'诊断结论：{report.diagnosis}')
    if report.follow_up_notes:
        lines.append(f'随访备注：{report.follow_up_notes}')
    return '\n'.join(lines)


def _medical_record_text(record):
    lines = []
    if record.visit_date:
        lines.append(f'就诊日期：{record.visit_date.strftime("%Y-%m-%d")}')
    if record.symptoms:
        lines.append(f'主诉与症状：{record.symptoms}')
    if record.diagnosis:
        lines.append(f'诊断：{record.diagnosis}')
    if record.treatment:
        lines.append(f'治疗方案：{record.treatment}')
    prescription = record.prescription
    if prescription:
        lines.append(f'处方：{prescription}')
    if record.advice:
        lines.append(f'医嘱：{record.advice}')
    if record.follow_up_date:
        lines.append(f'复诊日期：{record.follow_up_date.strftime("%Y-%m-%d")}')
    return '\n'.join(lines)


def _text_hash(value):
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()


def _mime_of(path):
    import mimetypes
    return mimetypes.guess_type(str(path))[0] or 'application/octet-stream'


def _extra_meta(meta):
    """frontmatter 里除已单列字段外的其余内容，原样留给文档元数据"""
    known = {'title', 'doc_type', 'department', 'source', 'origin', 'language'}
    return {k: v for k, v in (meta or {}).items() if k not in known}


def _dump_meta(extra, original_filename):
    import json
    data = dict(extra or {})
    if original_filename:
        # 存原始文件名供展示：中文文件名不能用于落盘（见 api/knowledge.py）
        data['original_filename'] = original_filename
    return json.dumps(data, ensure_ascii=False)


_pipeline = None


def get_pipeline():
    """进程内单例"""
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline()
    return _pipeline
