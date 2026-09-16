# 知识库语料说明

本目录是 RAG 知识库的语料与运行期存储。

## 目录结构

```
knowledge/
├── README.md          # 本文件
├── jieba_dict.txt     # 医学自定义词典（BM25 分词用）
├── corpus/            # 随仓库提交的语料，按 doc_type 分目录
│   ├── public/        # 从 PMC 开放获取子集抓取的文献（origin: public）
│   ├── classification/# 骨折分型（origin: curated）
│   ├── guideline/     # 诊疗原则
│   ├── rehab/         # 康复
│   ├── drug/          # 药物
│   └── anatomy/       # 解剖与影像
└── uploads/           # 运行期上传（不入库 git），yyyy/mm/<uuid4>.<ext>
```

## 语料来源与性质 —— 务必区分

知识库里有两类内容，**性质完全不同，前端引用卡片上会分别标注**：

### `origin: public` —— 公开资料原文

来自 **PMC 开放获取子集**（PubMed Central Open Access Subset），
经 NCBI E-utilities 抓取，每篇都有：

- 真实的 **PMCID** 与可访问的原文链接
- 明确的 **Creative Commons 授权**

抓取脚本：`backend/scripts/fetch_pmc_corpus.py`

**授权筛选规则**：只收录允许演绎的授权（CC BY、CC BY-NC 等），
**排除 ND（禁止演绎）**，因为把 JATS XML 转成 Markdown 属于演绎行为。
每篇的授权类型记录在 frontmatter 的 `license` 字段。

**相关性筛选**：排除动物实验、体外研究、基因关联研究、与骨折诊疗无关的
共病研究、单例个案报道。这些文献本身是真实的，但对面向临床问答的知识库
是噪声——被检索到并作为"参考资料"引用一篇小鼠基因研究的文章，
比没有这条资料更糟。

### `origin: curated` —— 本项目整理摘要

由本项目依据公开的分型框架与通行诊疗原则**整理编写**，
frontmatter 的 `source` 字段标明依据来源。

**这类内容不是原文，也不是任何指南的翻译。** 它用于：

- 说明分型的编码结构与临床含义
- 说明通行处理原则与康复分期思路
- 演示引用溯源功能

引用卡片上显示为「整理摘要」徽标，**不会**被当作权威指南引用。

### 关于医疗安全

整理摘要类文档遵循以下约束：

- **不编造统计数据**（如发病率、成功率等具体数字）
- **不给用药剂量、疗程与处方建议**，药物类文档只做类别与机制说明，
  并明确指向医嘱与药品说明书
- 康复类文档不提供个体化的负重时间表，明确指向主管医师医嘱

## 已入库语料清单

### 抓取的公开文献

见 `corpus/public/` 下各文件的 frontmatter，
包含 PMCID、原文 URL 与授权类型。筛选与抓取记录可通过
`python scripts/fetch_pmc_corpus.py --dry-run` 复现。

### 本项目整理的摘要

| 文档 | 说明 |
|---|---|
| `classification/ao-ota-总则.md` | AO/OTA 分型编码结构 |
| `classification/股骨远端骨折分型.md` | 股骨远端 33-A/B/C |
| `classification/胫骨平台骨折Schatzker分型.md` | Schatzker I–VI |
| `classification/股骨颈骨折Garden分型.md` | Garden I–IV 与血供 |
| `classification/踝关节骨折分型.md` | Danis-Weber 与 Lauge-Hansen |
| `classification/开放性骨折GustiloAnderson分型.md` | I/II/IIIa/IIIb/IIIc |
| `guideline/骨折急救与早期处理原则.md` | 急救、骨筋膜室综合征 |
| `guideline/骨质疏松性骨折诊疗原则.md` | 脆性骨折评估与干预 |
| `rehab/骨折康复分期总则.md` | 三期划分与判断标准 |
| `rehab/下肢骨折术后康复要点.md` | 负重分级、拐杖使用、DVT |
| `rehab/上肢骨折术后康复要点.md` | 各部位要点、活动度训练 |
| `drug/骨质疏松常用药物类别说明.md` | 药物类别（无剂量建议） |
| `anatomy/骨折影像学评估基础.md` | X 线/CT/MRI 选择与漏诊 |

## 个人病历

患者本人的病历与检测报告也会入库，但：

- `patient_id` 字段标明归属，**检索层强制过滤**（见
  `services/rag/retriever.py` 的 `RetrievalScope`）
- 与共享语料在**同一张表**，但共享行 `patient_id IS NULL`
- 前端的引用卡片上标注「本人病历」

### 只收临床事实，不收既往的 AI 解读

病历切片**刻意排除** `medical_advice.interpretation` 等 AI 生成的文本，
只保留：检查日期、检出类型与置信度、医生填写的诊断结论与随访备注
（见 `services/rag/pipeline.py::_detection_report_text`）。

原因是一个会自我强化的回路：

```
AI 解读 → 存进病历 → 切片入库 → 被检索为参考资料 → 下一代解读再引用它
```

两个后果：引用卡片标着「本人病历」而内容其实是 AI 写的，
患者会误以为是医生结论；以及上一轮的错误被当成"事实"逐轮放大。

解读文本在界面上照常看得到，只是不再充当知识源。
（对照：共享语料里的 `origin: curated` 整理稿也是本项目整理的，
但它们在界面上明确标为「整理摘要」，与「本人病历」区分。）

入库命令：`python scripts/ingest_knowledge.py --apply --patient-records`

## 扫描件政策

**无文本层的 PDF（扫描件）会被明确拒绝**，而不是入库一份空文档。

判定阈值：抽取文本少于 100 字，或平均每页少于 20 字。

此时文档以 `status=failed` 记录，`error_msg` 说明原因，
接口返回 422，管理界面显示为失败行。**不做静默成功。**

### OCR 的取舍

本项目**未实现 OCR**。理由是 OCR 需要外部二进制依赖
（Poppler/Tesseract 或 PaddleOCR 模型），且逐页识别成本高，
属于独立工程。若需支持扫描件，建议的接入点是在
`services/rag/loader.py::load_pdf` 中，当检测到无文本层时
调用 OCR 服务，而不是在入库流程里内联实现。

## 环境依赖

- **PostgreSQL + pgvector**：向量检索的前提。
  启停：`bash scripts/pg.sh start|stop|status`；
  引导检查：`python scripts/init_knowledge_db.py --check`
- 全新机器上初始化数据库（含 `CREATE EXTENSION vector`）：
  ```bash
  conda create -n ortho-pg -c conda-forge postgresql pgvector
  bash scripts/pg.sh start
  python scripts/init_knowledge_db.py --apply
  ```

## 常用命令

```bash
cd backend

# 建表 + pgvector 扩展 + HNSW/GIN 索引（应用启动时也会自动执行）
python scripts/init_knowledge_db.py --apply
python scripts/init_knowledge_db.py --check      # 断言是否齐备

# 入库语料
python scripts/ingest_knowledge.py                # 试运行
python scripts/ingest_knowledge.py --apply        # 实际入库
python scripts/ingest_knowledge.py --apply --replace   # 切片策略变更后重建

# 入库患者病历
python scripts/ingest_knowledge.py --apply --patient-records

# 检索验证（含跨患者泄漏与幻觉测试）
python scripts/verify_knowledge_base.py --with-models

# 抓取公开文献语料
python scripts/fetch_pmc_corpus.py --limit 3
python scripts/fetch_pmc_corpus.py --prune         # 按当前标准清理
```
