"""文档解析：PDF / DOCX / Markdown / 纯文本 → LoadedDoc

统一产出纯文本 + 元数据，并在合适的地方插入两个哨兵，供切片器还原结构：

- `<!-- page:N -->`：PDF 分页，切片时用于记录来源页码（引用溯源要显示"第N页"）
- markdown 标题：docx 的 `Heading N` 会被映射成 `#`，使两种格式共用一套
  标题层级，切片器只需要一条代码路径

扫描件（无文本层 PDF）**明确拒绝**而不是返回空文本——一份入库成功但检索不到
任何内容的文档，比一条清晰的失败记录有害得多。
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from utils.logger import logger

PAGE_SENTINEL = '<!-- page:{} -->'
_PAGE_RE = re.compile(r'^<!-- page:(\d+) -->$')

# 支持的扩展名 → 解析器标识
SUPPORTED_EXTENSIONS = {
    '.md': 'markdown',
    '.markdown': 'markdown',
    '.txt': 'text',
    '.pdf': 'pdf',
    '.docx': 'docx',
}

# 扫描件判定阈值：整篇少于 100 字，或平均每页少于 20 字
_MIN_TOTAL_CHARS = 100
_MIN_CHARS_PER_PAGE = 20

ORIGIN_PUBLIC = 'public'
ORIGIN_CURATED = 'curated'
ORIGIN_PATIENT_RECORD = 'patient_record'
VALID_ORIGINS = (ORIGIN_PUBLIC, ORIGIN_CURATED, ORIGIN_PATIENT_RECORD)


class LoadError(Exception):
    """文档解析失败（不支持的类型、文件损坏等）"""


class ScannedPdfError(LoadError):
    """PDF 无文本层，通常是扫描件"""


@dataclass
class LoadedDoc:
    text: str
    meta: dict = field(default_factory=dict)
    pages: int = 0                       # 1-based 总页数；无页概念为 0
    warnings: list = field(default_factory=list)

    @property
    def title(self):
        return self.meta.get('title', '')

    @property
    def char_count(self):
        """正文字数，不含哨兵"""
        return len(_strip_sentinels(self.text))


def _strip_sentinels(text):
    return '\n'.join(
        line for line in text.splitlines() if not _PAGE_RE.match(line.strip())
    )


def parse_frontmatter(raw):
    """拆出 YAML frontmatter，返回 (meta, 正文)

    没有 frontmatter 或格式错误都返回空 meta —— 由调用方补默认值，
    一份缺元数据的文档不该让整批入库失败。
    """
    if not raw.startswith('---'):
        return {}, raw
    parts = raw.split('\n')
    if parts[0].strip() != '---':
        return {}, raw
    for i in range(1, len(parts)):
        if parts[i].strip() in ('---', '...'):
            block = '\n'.join(parts[1:i])
            body = '\n'.join(parts[i + 1:])
            try:
                import yaml
                meta = yaml.safe_load(block) or {}
                if not isinstance(meta, dict):
                    return {}, raw
                return meta, body
            except Exception as e:
                logger.warning('frontmatter 解析失败，按无元数据处理: %s', e)
                return {}, raw
    return {}, raw


def infer_meta(meta, body, fallback_title):
    """补全元数据并校验

    origin 默认 **curated** 而不是 public：一份没标注来源性质的文件，
    按"整理摘要"对待是诚实的默认值，反过来则等于替它背书。
    """
    meta = dict(meta or {})
    if not meta.get('title'):
        match = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
        meta['title'] = (match.group(1).strip() if match
                         else (fallback_title or '未命名文档'))
    meta.setdefault('doc_type', 'other')
    meta.setdefault('department', '骨科')
    meta.setdefault('language', 'zh')
    meta.setdefault('origin', ORIGIN_CURATED)
    meta.setdefault('source', '')
    if meta['origin'] not in VALID_ORIGINS:
        logger.warning('未知 origin=%r，按 curated 处理', meta['origin'])
        meta['origin'] = ORIGIN_CURATED
    if not str(meta.get('source') or '').strip():
        # 出处是引用溯源的立身之本：没有 source 的切片被引用时，
        # 卡片上会显示一个空来源。多数情况是 frontmatter 写坏（如 YAML 里
        # 未加引号的冒号导致整段元数据解析失败），必须让使用者看见。
        logger.warning(
            '文档《%s》缺少 source（出处），引用溯源将显示空来源；'
            '请检查 frontmatter 是否被正确解析', meta.get('title'),
        )
    return meta


def load_markdown(path):
    raw = Path(path).read_text(encoding='utf-8', errors='replace')
    meta, body = parse_frontmatter(raw)
    return LoadedDoc(text=body.strip(), meta=meta, pages=0)


def load_text(path):
    raw = Path(path).read_text(encoding='utf-8', errors='replace')
    meta, body = parse_frontmatter(raw)
    return LoadedDoc(text=body.strip(), meta=meta, pages=0)


# 句末标点：这些字符结尾说明是真正的句子/段落结束，不是排版折行
_TERMINAL_CHARS = '。！？；：!?;:…）)」』】》”"．.'


def _rejoin_wrapped_lines(text):
    """合并 PDF 因排版折行产生的换行

    PDF 的每行是按版面宽度硬折的，换行常落在句子中间：
        「骨质疏松性骨折是中老年最常见的骨骼疾病 ，¶
          也是骨质疏松症的严重阶段 ，具有发病率高 、致残¶
          致死率高、医疗花费高的特点 。」
    若原样保留，切片器会把换行当成句子边界，切出的片段从半句话开始，
    读起来是断的，重叠回带也跟着错位。

    判据（启发式）：
    - 上一行的**长度接近本页行宽** → 说明它是被折行的正文行，不是短标题
    - 且**不以句末标点结尾** → 说明话没说完
    同时满足则与下一行合并。"排满一行"这条不能省：
    否则标题、作者、页眉这些短行会被粘成一坨。
    """
    lines = [line.rstrip() for line in text.split('\n')]
    body_lengths = sorted(len(line.strip()) for line in lines if len(line.strip()) >= 8)
    if len(body_lengths) < 4:
        return text                      # 行数太少，判断不出行宽

    width = body_lengths[len(body_lengths) // 2]        # 用中位数而非最大值：
    threshold = max(8, int(width * 0.8))                # 页眉页脚往往比正文长得多
    max_reasonable = int(width * 1.3)

    merged = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            merged.append('')
            continue
        if (merged and merged[-1]
                and len(merged[-1]) <= max_reasonable
                and len(merged[-1]) >= threshold
                and merged[-1][-1] not in _TERMINAL_CHARS):
            merged[-1] = merged[-1] + stripped
        else:
            merged.append(stripped)
    return '\n'.join(merged)


def _strip_running_headers(pages):
    """去掉在多数页面上重复出现的行（页眉、页脚、刊名栏）

    医学期刊的 PDF 每页顶部都有相同的刊名与页码，逐页抽取后这些行会混进
    正文，既占切片额度又污染检索——它们和正文内容毫无关系。
    判据：在超过半数页面上出现的同一行，几乎不可能是正文。
    """
    if len(pages) < 3:
        return pages

    def signature(line):
        """去掉数字与分隔符后的"骨架"

        页眉每页只有页码不同（`… ·1·` / `… ·2·`），精确比对匹配不上，
        必须先归一化。
        """
        return re.sub(r'[\d\s·\-—–_.·,]+', '', line)

    from collections import Counter
    counter = Counter()
    for page in pages:
        seen = {signature(line.strip())
                for line in page.split('\n') if line.strip()}
        for sig in seen:
            counter[sig] += 1

    threshold = max(2, len(pages) // 2)
    repeated = {sig for sig, count in counter.items()
                if count >= threshold and len(sig) >= 6}

    cleaned = []
    for page in pages:
        kept = [line for line in page.split('\n')
                if line.strip() and signature(line.strip()) not in repeated]
        cleaned.append('\n'.join(kept))
    return cleaned


# 中文文档的编号标题：`一、定义`、`（二）影像学检查`
# 只认这两种。`1.` / `2.` 不认——实测某指南里 42 处 `1.` 大多是表格中的
# "1.诊断 2.治疗"，提升成标题会把检索结构切得乱七八糟。
_PDF_HEADING_PATTERNS = (
    (re.compile(r'^[一二三四五六七八九十]+、\s*\S'), 2),
    (re.compile(r'^[（(][一二三四五六七八九十]+[）)]\s*\S'), 3),
)
_PDF_HEADING_MAX_LEN = 34


def _promote_headings(text):
    """把中文编号标题提升为 markdown 标题，让 PDF 也有章节结构

    PDF 没有标题样式可言，全文扁平。切片器是按标题层级切的，
    没有标题就没有 section——引用卡片上只能显示书名，读者无从定位。
    识别出编号标题后，PDF 与 markdown 走同一套切片逻辑。
    """
    out = []
    for line in text.split('\n'):
        stripped = line.strip()
        level = None
        if stripped and len(stripped) <= _PDF_HEADING_MAX_LEN and not stripped.endswith('。'):
            for pattern, candidate in _PDF_HEADING_PATTERNS:
                if pattern.match(stripped):
                    level = candidate
                    break
        out.append('#' * level + ' ' + stripped if level else line)
    return '\n'.join(out)


def load_pdf(path):
    """解析 PDF，逐页插入分页哨兵

    无文本层（扫描件）直接抛 ScannedPdfError，不返回空文档。
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        pages = len(reader.pages)
        raw_pages = []
        for i, page in enumerate(reader.pages, start=1):
            try:
                raw_pages.append(page.extract_text() or '')
            except Exception as e:          # 单页解析失败不应毁掉整篇
                logger.warning('PDF 第 %d 页解析失败: %s', i, e)
                raw_pages.append('')
        # 顺序要紧：先去页眉页脚（它们会干扰行宽判断），再合并折行
        # 顺序要紧：先去页眉页脚（它们会干扰行宽判断），再合并折行，
        # 最后才认标题（折行合并后标题才可能独占一行）
        cleaned = _strip_running_headers(raw_pages)
        parts = [
            f'{PAGE_SENTINEL.format(i)}\n'
            f'{_promote_headings(_rejoin_wrapped_lines(text)).strip()}'
            for i, text in enumerate(cleaned, start=1)
        ]
    except Exception as e:
        raise LoadError(f'PDF 解析失败: {e}') from e

    text = '\n\n'.join(parts)
    body_chars = len(_strip_sentinels(text).strip())

    if body_chars < _MIN_TOTAL_CHARS or (
            pages and body_chars / pages < _MIN_CHARS_PER_PAGE):
        raise ScannedPdfError(
            '该 PDF 无文本层（扫描件），请上传可复制文字的 PDF 或先做 OCR'
        )

    return LoadedDoc(text=text, meta={}, pages=pages)


def load_docx(path):
    """解析 DOCX，按文档顺序交错输出段落与表格

    必须按 body 顺序遍历：先取 doc.paragraphs 再取 doc.tables 会把表格
    全部挪到末尾，医学文档里的表格一旦脱离上下文就失去了意义。
    """
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = Document(str(path))
    except Exception as e:
        raise LoadError(f'DOCX 解析失败: {e}') from e

    lines = []
    for child in document.element.body.iterchildren():
        if child.tag == qn('w:p'):
            para = Paragraph(child, document)
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name or '') if para.style is not None else ''
            match = re.match(r'Heading\s+(\d+)', style)
            if match:
                lines.append('#' * int(match.group(1)) + ' ' + text)
            elif style == 'Title':
                lines.append('# ' + text)
            else:
                lines.append(text)
        elif child.tag == qn('w:tbl'):
            table = Table(child, document)
            lines.append(_table_to_markdown(table))

    return LoadedDoc(text='\n\n'.join(lines), meta={}, pages=0)


def _table_to_markdown(table):
    """把 DOCX 表格转成 markdown 表格

    切片器把连续的 `|` 行当作一个不可分割的表格块，因此这里必须输出
    规范的 markdown 表格，而不是纯文本拼贴。
    """
    rows = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            value = ' '.join(cell.text.split())
            cells.append(value.replace('|', '\\|'))
        rows.append('| ' + ' | '.join(cells) + ' |')
    if not rows:
        return ''
    if len(rows) >= 1:
        header_sep = '| ' + ' | '.join(['---'] * len(table.rows[0].cells)) + ' |'
        rows.insert(1, header_sep)
    return '\n'.join(rows)


def load_document(path, fallback_title=None):
    """按扩展名分派解析器

    fallback_title 用于上传场景：落盘名是 uuid，直接拿它当标题
    会得到一串谁也认不出的字符，应改用客户端原名。
    """
    path = Path(path)
    if not path.exists():
        raise LoadError(f'文件不存在: {path}')
    ext = path.suffix.lower()
    kind = SUPPORTED_EXTENSIONS.get(ext)
    if kind is None:
        raise LoadError(
            f'不支持的文件类型 {ext}，仅支持 '
            + '、'.join(sorted(SUPPORTED_EXTENSIONS))
        )

    loader = {
        'markdown': load_markdown,
        'text': load_text,
        'pdf': load_pdf,
        'docx': load_docx,
    }[kind]

    doc = loader(path)
    doc.meta = infer_meta(doc.meta, doc.text, fallback_title or path.stem)
    return doc


def load_text_document(text, *, title, meta=None):
    """从已有文本构造文档（患者病历等 DB 派生的内容）"""
    meta = dict(meta or {})
    meta.setdefault('title', title)
    meta.setdefault('origin', ORIGIN_PATIENT_RECORD)
    meta.setdefault('doc_type', 'record')
    meta = infer_meta(meta, text, title)
    return LoadedDoc(text=text, meta=meta, pages=0)
