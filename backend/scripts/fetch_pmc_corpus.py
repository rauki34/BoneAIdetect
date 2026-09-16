"""从 PMC 开放获取子集抓取骨科文献，转成知识库语料

**为什么要抓而不是全自己写**：知识库的价值取决于内容有没有出处。
这些文章有真实 DOI/PMCID、明确的 CC 授权和可核查的原文，引用卡片上
可以诚实地标成「公开原文」。与之相对，本项目自己整理的文档标成「整理摘要」，
两者在界面上区分显示，不混淆。

只抓 PMC 开放获取子集（OA subset），并且**跳过 ND（禁止演绎）授权**——
我们需要把 XML 转成 Markdown，那属于演绎。授权类型写进每篇的 frontmatter。

用法：
    cd backend
    python scripts/fetch_pmc_corpus.py              # 抓取（跳过已存在的）
    python scripts/fetch_pmc_corpus.py --limit 3    # 每个主题最多抓几篇
    python scripts/fetch_pmc_corpus.py --dry-run    # 只搜索不下载
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

OUT_DIR = BACKEND / 'knowledge' / 'corpus' / 'public'
EUTILS = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'

# NCBI 要求无 API key 时不超过 3 请求/秒；取 1 秒间隔留足余量
REQUEST_INTERVAL = 1.1

class LicenseError(Exception):
    """授权不满足收录条件"""

# 主题 → (检索式, doc_type, 子目录)
#
# 检索式刻意限定在"临床诊疗"上。早先写成 `X fracture classification` 时，
# 命中大量"某术式治疗某骨折的疗效分析"，放进"分型"目录是名不副实的。
TOPICS = [
    ('distal femur fracture OR tibial plateau fracture classification system review',
     'classification', 'fracture_classification'),
    ('proximal humerus fracture classification Neer treatment decision',
     'classification', 'fracture_classification'),
    ('femoral neck fracture Garden classification management elderly',
     'classification', 'fracture_classification'),
    ('ankle fracture classification Danis-Weber Lauge-Hansen',
     'classification', 'fracture_classification'),
    ('distal radius fracture treatment guideline adults', 'guideline', 'fracture_treatment'),
    ('hip fracture elderly patient management guidelines', 'guideline', 'fracture_treatment'),
    ('osteoporotic vertebral compression fracture treatment guideline', 'guideline', 'fracture_treatment'),
    ('open fracture Gustilo-Anderson classification antibiotic management', 'guideline', 'fracture_treatment'),
    ('fracture rehabilitation protocol physical therapy exercise', 'rehab', 'rehabilitation'),
    ('hip fracture postoperative rehabilitation outcome', 'rehab', 'rehabilitation'),
    ('deep vein thrombosis prophylaxis orthopedic trauma guideline', 'guideline', 'complications'),
    ('fracture related infection prevention diagnosis management', 'guideline', 'complications'),
    ('fracture healing process stages clinical', 'guideline', 'bone_healing'),
    ('bisphosphonate osteoporosis fracture prevention clinical', 'drug', 'drug'),
    ('osteoporosis pharmacotherapy fracture risk guideline', 'drug', 'drug'),
]

# 标题命中即拒收：基础研究、动物实验、基因关联、无关共病
#
# 这些文章本身是真实的公开文献，但对一个面向临床问答的知识库而言是噪声——
# 被检索到并作为"参考资料"引用研究小鼠基因的文章，比没有这条资料更糟。
EXCLUDE_TITLE_PATTERNS = [
    # 动物 / 体外
    r'\bmice\b', r'\bmouse\b', r'\brats?\b', r'\bmurine\b', r'\brabbits?\b',
    r'\bovine\b', r'\bcanine\b', r'\bporcine\b', r'\bbovine\b', r'\bzebrafish\b',
    r'\bin vitro\b', r'\bex vivo\b', r'experimental model', r'animal model',
    # 基础科学 / 分子
    r'\bosteoblasts?\b', r'\bosteoclasts?\b', r'\bchondrocytes?\b',
    r'gene expression', r'\bpolymorphisms?\b', r'signaling pathway',
    r'\bmolecular\b', r'\bgenetic\b', r'\bgenomic\b', r'\btranscriptom',
    # 与骨折诊疗无关的共病
    r'\bHIV\b', r'\bhepatitis\b', r'\bCOVID\b', r'\bSARS\b',
    # 单例个案报道，证据层级过低
    r'\bcase report\b',
]

_EXCLUDE_RE = re.compile('|'.join(EXCLUDE_TITLE_PATTERNS), re.IGNORECASE)


def is_relevant(title):
    """标题是否属于面向临床的知识（False 表示应当拒收）"""
    return not _EXCLUDE_RE.search(title or '')

# JATS 里这些节点不承载正文，跳过
SKIP_TAGS = {'ref-list', 'back', 'fig', 'table-wrap-foot', 'fn-group',
             'ack', 'front', 'processing-meta', 'journal-meta', 'article-meta'}


def http_get(url, *, binary=False):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'ortho-knowledge-base/1.0 (graduation project; contact: local)',
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    return data if binary else data.decode('utf-8', errors='replace')


def esearch(term, retmax):
    params = urllib.parse.urlencode({
        'db': 'pmc', 'term': f'{term} AND "open access"[filter]',
        'retmax': retmax, 'retmode': 'json', 'sort': 'relevance',
    })
    payload = json.loads(http_get(f'{EUTILS}/esearch.fcgi?{params}'))
    return payload.get('esearchresult', {}).get('idlist', [])


def efetch(pmcid):
    params = urllib.parse.urlencode({'db': 'pmc', 'id': pmcid, 'retmode': 'xml'})
    return http_get(f'{EUTILS}/efetch.fcgi?{params}')


def text_of(node):
    """取节点的全部文本，保留段落内空白归一"""
    return re.sub(r'\s+', ' ', ''.join(node.itertext())).strip()


def license_of(root):
    """取 <license_ref> 里的授权 URL（JATS 里用 ali 命名空间）"""
    for node in root.iter():
        if node.tag.endswith('license_ref') and (node.text or '').strip():
            return node.text.strip()
    return ''


def classify_license(href):
    """判断授权是否允许我们收录

    返回 (code, ok)：
    - ok=True  允许演绎（格式转换），可收录
    - ok=False 含 ND（禁止演绎），或无法识别

    Creative Commons 的授权码在 URL 的 /licenses/<code>/ 段里，是 `by`、
    `by-nc`、`by-nc-nd` 这样的形式，**不是** `ccby`。按后者匹配会把所有
    合规文章误判为不合规。
    """
    if not href:
        return '', False
    lowered = href.lower()
    if 'publicdomain' in lowered:          # CC0 / Public Domain Mark
        return 'publicdomain', True
    match = re.search(r'/licenses/([a-z0-9\-]+)/', lowered)
    if not match:
        return '', False
    code = match.group(1)
    # ND 出现在授权码的分段里才算禁止演绎，避免 'and'/'standard' 之类误伤
    if 'nd' in code.split('-'):
        return code, False
    return code, True


def render_table(table_node):
    rows = []
    for tr in table_node.iter('tr'):
        cells = [text_of(td).replace('|', '\\|') for td in tr if td.tag in ('td', 'th')]
        if cells:
            rows.append('| ' + ' | '.join(cells) + ' |')
    if not rows:
        return []
    if len(rows) > 1:
        width = rows[0].count('|') - 1
        rows.insert(1, '| ' + ' | '.join(['---'] * max(1, width)) + ' |')
    return rows


def render_section(sec, depth, out):
    """递归渲染 <sec>：标题层级即 JATS 的嵌套层级"""
    title = sec.find('title')
    if title is not None:
        out.append('#' * min(depth + 1, 6) + ' ' + text_of(title))
        out.append('')

    for child in sec:
        if child.tag in SKIP_TAGS or child.tag == 'title':
            continue
        if child.tag == 'sec':
            render_section(child, depth + 1, out)
        elif child.tag == 'p':
            text = text_of(child)
            if text:
                out.append(text)
                out.append('')
        elif child.tag == 'list':
            for item in child.findall('list-item'):
                text = text_of(item)
                if text:
                    out.append(f'- {text}')
            out.append('')
        elif child.tag in ('table-wrap', 'table'):
            for table in ([child] if child.tag == 'table' else child.iter('table')):
                out.extend(render_table(table))
                out.append('')


def to_markdown(root):
    parts = []

    title_node = root.find('.//article-title')
    title = text_of(title_node) if title_node is not None else '未命名文献'
    parts.append(f'# {title}')
    parts.append('')

    abstract = root.find('.//abstract')
    if abstract is not None:
        parts.append('## 摘要')
        parts.append('')
        body_text = text_of(abstract)
        if body_text:
            parts.append(body_text)
            parts.append('')

    # 只渲染正文顶层 sec；front/back 由 to_markdown 的调用方排除
    body = root.find('.//body')
    if body is not None:
        for sec in body.findall('sec'):
            render_section(sec, 1, parts)
        # body 里的裸段落（不在 sec 内）
        for para in body.findall('p'):
            text = text_of(para)
            if text:
                parts.append(text)
                parts.append('')

    return title, '\n'.join(parts).strip()


def frontmatter(meta):
    lines = ['---']
    for key, value in meta.items():
        if value is None:
            continue
        safe = str(value).replace('"', "'").replace('\n', ' ')
        lines.append(f'{key}: "{safe}"')
    lines.append('---')
    lines.append('')
    return '\n'.join(lines)


def main():
    from core.bootstrap import enable_utf8_console
    enable_utf8_console()

    limit = 3
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    dry_run = '--dry-run' in sys.argv

    if '--prune' in sys.argv:
        print('按当前标准清理已抓取的文件')
        return prune_existing()

    if '--trim' in sys.argv:
        keep = int(sys.argv[sys.argv.index('--trim') + 1])
        print(f'每个主题目录只保留 {keep} 篇')
        return trim_per_topic(keep)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f'输出目录: {OUT_DIR}')
    print(f'每主题最多 {limit} 篇{"（试运行）" if dry_run else ""}\n')

    stats = {'fetched': 0, 'skipped_license': 0, 'skipped_exists': 0,
             'failed': 0, 'no_text': 0, 'skipped_irrelevant': 0}

    for term, doc_type, subdir in TOPICS:
        print(f'[检索] {term}')
        try:
            ids = esearch(term, limit * 3)
        except Exception as e:
            print(f'  搜索失败: {e}')
            stats['failed'] += 1
            continue
        time.sleep(REQUEST_INTERVAL)

        target_dir = OUT_DIR / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        taken = 0

        for pmcid in ids:
            if taken >= limit:
                break
            out_path = target_dir / f'PMC{pmcid}.md'
            if out_path.exists():
                stats['skipped_exists'] += 1
                taken += 1
                continue

            try:
                xml = efetch(pmcid)
            except Exception as e:
                print(f'  {pmcid} 下载失败: {e}')
                stats['failed'] += 1
                continue
            finally:
                time.sleep(REQUEST_INTERVAL)

            try:
                root = ET.fromstring(xml)
            except ET.ParseError as e:
                print(f'  {pmcid} XML 解析失败: {e}')
                stats['failed'] += 1
                continue

            license_href = license_of(root)
            license_code, usable = classify_license(license_href)
            if not usable:
                print(f'  {pmcid} 跳过：授权不允许收录（{license_href or "未标注"}）')
                stats['skipped_license'] += 1
                continue

            title, markdown = to_markdown(root)

            if not is_relevant(title):
                print(f'  {pmcid} 跳过：非临床内容（{title[:56]}）')
                stats['skipped_irrelevant'] += 1
                continue

            if len(markdown) < 2000:
                print(f'  {pmcid} 跳过：正文过短（{len(markdown)} 字符，可能是摘要级条目）')
                stats['no_text'] += 1
                continue

            if dry_run:
                print(f'  [试运行] {pmcid} {title[:60]}（{len(markdown)} 字符）')
                taken += 1
                stats['fetched'] += 1
                continue

            meta = {
                'title': title,
                'doc_type': doc_type,
                'department': '骨科',
                'origin': 'public',
                'language': 'en',
                'source': f'PMC{pmcid} · {license_href}',
                'pmcid': f'PMC{pmcid}',
                'license': license_href,
                'license_code': license_code,
                'url': f'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/',
            }
            out_path.write_text(frontmatter(meta) + markdown, encoding='utf-8')
            print(f'  [已保存] {pmcid} {title[:56]}（{len(markdown)} 字符）')
            taken += 1
            stats['fetched'] += 1

    print('\n' + '=' * 62)
    print(f'  抓取 {stats["fetched"]} 篇 / 已存在 {stats["skipped_exists"]} 篇 / '
          f'授权不符 {stats["skipped_license"]} 篇 / 非临床 {stats["skipped_irrelevant"]} 篇 / '
          f'正文过短 {stats["no_text"]} 篇 / 失败 {stats["failed"]} 篇')
    return 0 if stats['fetched'] or stats['skipped_exists'] else 1


REVIEW_HINT_RE = re.compile(
    r'review|guideline|consensus|classification|management|protocol|'
    r'epidemiolog|overview|update|systematic', re.IGNORECASE)


def trim_per_topic(keep):
    """每个主题目录只保留最值得收录的 keep 篇

    为什么需要：这些是英文文献，而系统面向中文使用者。若英文切片在数量上
    压倒性占优（初抓时 5190 : 0），中文提问几乎必然检索到英文资料，
    引用卡片上给中文医生看英文标题——检索演示会与实际用途脱节。

    取舍依据：优先"综述/指南/分型/共识"类，同类里优先篇幅大的（更全面）。
    这不是在筛选"正确性"，公开文献本身都是真实的；只是在挑对本系统
    最有用的一批，并如实记录删掉了哪些。
    """
    removed, kept = [], 0
    for folder in sorted(OUT_DIR.iterdir()):
        if not folder.is_dir():
            continue
        entries = []
        for path in sorted(folder.glob('*.md')):
            head = path.read_text(encoding='utf-8')[:800]
            match = re.search(r'title: "(.+?)"', head)
            title = match.group(1) if match else path.name
            entries.append((
                1 if REVIEW_HINT_RE.search(title) else 0,
                path.stat().st_size,
                path, title,
            ))
        entries.sort(key=lambda e: (-e[0], -e[1]))
        for _, _, path, title in entries[keep:]:
            path.unlink()
            removed.append((folder.name, title))
        kept += min(len(entries), keep)

    for folder, title in removed:
        print(f'  [删除] {folder:24} {title[:70]}')
    print(f'\n  保留 {kept} 篇，删除 {len(removed)} 篇')
    return 0


def prune_existing():
    """删除历史上已抓取、但按当前相关性与授权标准不应收录的文件

    筛选标准会随认知变化，重跑不能只影响新文件，否则库里会长期留着
    早期误收的内容。
    """
    removed, kept = [], 0
    for path in sorted(OUT_DIR.rglob('*.md')):
        head = path.read_text(encoding='utf-8')[:800]
        match = re.search(r'title: "(.+?)"', head)
        title = match.group(1) if match else ''
        license_match = re.search(r'license: "(.+?)"', head)
        license_code, usable = classify_license(
            license_match.group(1) if license_match else '')

        if not is_relevant(title) or not usable:
            reason = '非临床内容' if not is_relevant(title) else '授权不符'
            removed.append((path, reason, title))
        else:
            kept += 1

    for path, reason, title in removed:
        path.unlink()
        print(f'  [删除] {path.name} {reason}: {title[:58]}')
    print(f'\n  删除 {len(removed)} 篇 / 保留 {kept} 篇')
    return 0


if __name__ == '__main__':
    sys.exit(main())
