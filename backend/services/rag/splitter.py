"""医学文档切片

切片策略针对医疗文档的两个特点设计：

1. **结构即语义**：诊疗指南的内容严格挂在标题层级下（"3 分型标准 > 3.2 股骨远端"），
   因此按标题切分，并让每个切片都记住自己的标题路径——引用溯源要显示它。
2. **表格不可切**：分型表、剂量表被从中间截断就会产生错误信息（半张分型表
   比没有表更糟），所以表格是原子块，超长也整体保留。

切片正文里重复了 `标题 · 章节` 头。这看着冗余，但医疗文本大量使用"该方法"
"上述分型"这类指代，脱离标题后单看正文无法消解——约 20 token 的代价换回
真实的召回率提升，值得。
"""
import re
from dataclasses import dataclass

from services.rag.loader import PAGE_SENTINEL
from utils.logger import logger

_PAGE_RE = re.compile(r'^<!-- page:(\d+) -->$')
_HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[。！？；\n])|(?<=[.!?])\s+')


def count_tokens(text):
    """估算 token 数

    刻意不引入 tokenizer：切片器要保持纯函数、可单测，也不该为了数数
    付出十秒的模型加载。bge-m3 用的是 XLM-R sentencepiece，中文约 1 字
    1 token、英文约 1.3 词 1 token，按此估算足够支撑阈值判断。
    """
    cjk = sum(1 for ch in text if '一' <= ch <= '鿿')
    words = len(re.findall(r'[A-Za-z0-9]+', text))
    return cjk + int(words * 1.3)


@dataclass
class Chunk:
    content: str
    chunk_index: int
    section: str
    page: int | None
    token_count: int


def _tokenize_blocks(text):
    """把正文拆成块

    返回 [(kind, ...)]，kind ∈ pagebreak / heading / para / table / code。
    表格与代码块各自聚合为**一个**块，是后续"不切断"的前提。
    """
    lines = text.split('\n')
    blocks = []
    i, n = 0, len(lines)

    while i < n:
        stripped = lines[i].strip()

        if not stripped:
            i += 1
            continue

        match = _PAGE_RE.match(stripped)
        if match:
            blocks.append(('pagebreak', int(match.group(1))))
            i += 1
            continue

        match = _HEADING_RE.match(stripped)
        if match:
            blocks.append(('heading', len(match.group(1)), match.group(2).strip()))
            i += 1
            continue

        if stripped.startswith('```'):
            buf = [lines[i]]
            i += 1
            while i < n and not lines[i].strip().startswith('```'):
                buf.append(lines[i])
                i += 1
            if i < n:
                buf.append(lines[i])
                i += 1
            blocks.append(('code', '\n'.join(buf)))
            continue

        if stripped.startswith('|'):
            buf = []
            while i < n and lines[i].strip().startswith('|'):
                buf.append(lines[i].strip())
                i += 1
            blocks.append(('table', '\n'.join(buf)))
            continue

        buf = []
        while i < n:
            current = lines[i].strip()
            if (not current or _PAGE_RE.match(current)
                    or current.startswith('#') or current.startswith('|')
                    or current.startswith('```')):
                break
            buf.append(current)
            i += 1
        if buf:
            blocks.append(('para', '\n'.join(buf)))
        else:
            i += 1

    return blocks


class MedicalSplitter:
    """按标题层级 + 段落语义切片"""

    CHUNK_SIZE = 512
    OVERLAP = 64
    MIN_CHUNK_TOKENS = 60      # 只有标题没有正文的块并入下一块
    MAX_CHUNK_TOKENS = 900     # 硬上限，表格除外

    def split(self, doc):
        blocks = self._explode_oversized(_tokenize_blocks(doc.text))
        title = doc.meta.get('title', '')

        chunks = []
        section_stack = []          # [(level, title)]
        current_page = None

        buf = []                    # [(kind, text)]
        buf_tokens = 0
        buf_section = ''
        buf_page = None
        pending = ''                # 待并入下一块的重叠文本（按句回带）
        pending_section = None

        def section_path():
            # 首级标题常常就是文档标题（`# 股骨远端骨折`），拼进去会得到
            # "股骨远端骨折 · 股骨远端骨折 > 1 概述" 这种重复的头部
            titles = [t for _, t in section_stack]
            if titles and titles[0].strip() == title.strip():
                titles = titles[1:]
            return ' > '.join(titles)

        def flush():
            """结算当前缓冲为一个切片，并把尾句留作下一块的重叠"""
            nonlocal buf, buf_tokens, pending, pending_section
            if not buf:
                return
            body = '\n\n'.join(text for _, text in buf)
            content = self._compose(title, buf_section, body)
            chunks.append(Chunk(
                content=content,
                chunk_index=len(chunks),
                section=buf_section,
                page=buf_page,
                token_count=count_tokens(content),
            ))
            pending = self._tail_sentences(body, self.OVERLAP)
            pending_section = buf_section
            buf, buf_tokens = [], 0

        def start():
            """开新缓冲，若上一块同节则带上重叠"""
            nonlocal buf, buf_tokens, buf_section, buf_page
            buf, buf_tokens = [], 0
            buf_section = section_path()
            buf_page = current_page
            if pending and pending_section == buf_section:
                buf.append(('overlap', pending))
                buf_tokens = count_tokens(pending)

        for block in blocks:
            kind = block[0]

            if kind == 'pagebreak':
                current_page = block[1]
                continue

            if kind == 'heading':
                level, heading = block[1], block[2]
                # 一律在标题处切分。曾按"填充度 >= 30% 才切"来减少碎块，
                # 结果是小节被并进上一节，切片带着 2.1 的标题却装着 2.2 的正文——
                # 引用溯源给出错误的章节比切片偏小严重得多。
                flush()
                while section_stack and section_stack[-1][0] >= level:
                    section_stack.pop()
                section_stack.append((level, heading))
                continue

            text = block[1]
            tokens = count_tokens(text)

            # 表格/代码块不与正文混装，否则后续按尺寸切分时会把它拦腰截断
            if kind in ('table', 'code') and buf_tokens > 0:
                flush()

            if buf_tokens and buf_tokens + tokens > self.MAX_CHUNK_TOKENS:
                flush()

            if not buf:
                start()

            if kind == 'table' and tokens > self.MAX_CHUNK_TOKENS:
                # 超长表格整体保留，并明确标注未被截断
                logger.info('表格块超过硬上限（%d token），整体保留不切分', tokens)
                text = f'<!-- 表格较大，未截断 -->\n{text}'

            buf.append((kind, text))
            buf_tokens += tokens

        flush()
        return self._merge_heading_only(chunks)

    def _merge_heading_only(self, chunks):
        """把"只有标题没有正文"的切片并入相邻切片

        连续两个标题（`## 2 分型标准` 紧跟 `### 2.1 AO/OTA`）会产生一个只有
        标题行的切片，它对检索毫无价值。并入**下一块**并沿用下一块的 section：
        下一个标题是当前标题的子节点，用更精确的子节点标注仍然成立；
        并入上一块则会让正文挂到错误的章节下。
        """
        result = []
        pending = []            # 攒着的空标题块，等下一个有正文的块来收编

        for chunk in chunks:
            if chunk.token_count < self.MIN_CHUNK_TOKENS:
                pending.append(chunk)
                continue
            if pending:
                bodies = [c.content for c in pending] + [chunk.content]
                chunk.content = '\n\n'.join(bodies)
                chunk.token_count = count_tokens(chunk.content)
                pending = []
            result.append(chunk)

        if pending:
            # 文档以标题结尾（没有后续正文），只能往前并
            if result:
                tail = result[-1]
                tail.content = '\n\n'.join([tail.content] + [c.content for c in pending])
                tail.token_count = count_tokens(tail.content)
            else:
                result = pending        # 整篇只有一个标题，保持原样
        for i, chunk in enumerate(result):
            chunk.chunk_index = i
        return result

    def _explode_oversized(self, blocks):
        """把超长段落块按句拆成多个块

        必需的一步：块间切分管不到"单个段落本身就超限"的情况，而医学文档里
        整段不分行的写法很常见。若放任其成为超长切片，嵌入时会被 bge-m3 的
        max_seq_length 悄悄截断——那部分内容进得了库、却永远检索不到，
        表面上看不出任何异常。

        表格与代码块不拆：半张分型表比没有表更危险，这个取舍是有意的。
        """
        result = []
        for block in blocks:
            if block[0] != 'para' or count_tokens(block[1]) <= self.CHUNK_SIZE:
                result.append(block)
                continue
            for piece in self._pack_sentences(block[1], self.CHUNK_SIZE):
                result.append(('para', piece))
        return result

    @staticmethod
    def _pack_sentences(text, target):
        """按句打包到不超过 target token

        单句本身就超限时只能硬切——句子边界已经保不住了，但至少保证
        不会超过模型窗口而被静默截断。
        """
        sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s and s.strip()]
        out, buf, total = [], [], 0
        for sentence in sentences:
            tokens = count_tokens(sentence)
            if tokens > target:
                if buf:
                    out.append(''.join(buf))
                    buf, total = [], 0
                step = max(1, target)      # 中英混排下按字切足够安全
                for i in range(0, len(sentence), step):
                    out.append(sentence[i:i + step])
                continue
            if buf and total + tokens > target:
                out.append(''.join(buf))
                buf, total = [], 0
            buf.append(sentence)
            total += tokens
        if buf:
            out.append(''.join(buf))
        return out

    @staticmethod
    def _compose(title, section, body):
        header = f'{title} · {section}' if section else title
        return f'{header}\n\n{body}' if header else body

    @staticmethod
    def _tail_sentences(text, target_tokens):
        """从尾部按句取够 target_tokens，作为下一块的重叠

        按句而不是按字符回带：半句话进入下一块会污染检索到的语义。
        """
        if target_tokens <= 0:
            return ''
        sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s and s.strip()]
        picked = []
        total = 0
        for sentence in reversed(sentences):
            total += count_tokens(sentence)
            picked.append(sentence)
            if total >= target_tokens:
                break
        return ''.join(reversed(picked)).strip()
