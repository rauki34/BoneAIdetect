# 智慧骨科云平台

[English](README.md) | **中文**

一个面向骨科诊疗的全栈平台，围绕三块 AI 能力构建：**基于 YOLO 的骨折检测**、**临床语料上的混合检索（RAG）**，以及**能调用工具的患者康复助手 Agent**。

本仓库的工程重心在**后端与 AI 层**：Flask 服务 + PostgreSQL/pgvector + Redis + Celery，配一个与 provider 无关的 LLM 接入层、一条混合检索流水线，以及一套会规划、会调工具、带分层记忆的 Agent 运行时。（前端是 Vue 3，见[项目结构](#项目结构)。）

---

## 亮点

### 1. 混合检索 RAG，且检索质量有实测数字

检索分四步：**pgvector HNSW**（bge-m3，1024 维）与 **BM25**（jieba 分词）并行召回，用 **RRF** 融合，再由 **bge-reranker-v2-m3** 重排。每个回答都带引用，可回溯到具体切片（`index / doc / section / page / chunk_id / score` 六键契约）。

在 52 条评测集上实测（见[评测体系](#4-评测体系)）——32 条知识问答 + 5 条库外问题：

| 配置 | hit@1 | hit@5 | MRR | P50 延迟 |
|---|---|---|---|---|
| 纯向量 | 75.0% | 96.9% | 0.846 | 75 ms |
| 混合（无重排） | 90.6% | 100.0% | 0.953 | 77 ms |
| 混合 + 重排 | 90.6% | 100.0% | 0.948 | 436 ms |

这张表说了两件**只看 A/B/C 三组配置会看不出来**的事：

- **排序收益来自 BM25，不来自重排。** 加交叉编码器花了约 6 倍延迟，排序没有变好（MRR 甚至略降）。是我多加的第四组配置让这件事显形。
- **重排的真正贡献是"可判定的相关度"。** RRF 是排名分（`1/(60+rank)`），"能答"与"答不了"两类问题落在几乎同一条带上 —— 安全间隔只有 **0.0003**，做不了阈值判定；重排后两类分开 **0.80**，这才让第 2 节那道相关度闸门成立。

### 2. Agent：工具调用、规划与分层记忆

患者端的康复助手：模型**自己决定去查什么**，而不是接收预先塞好的上下文。

- **5 个只读工具** —— 指南检索、本人病历、本人档案（过敏史/既往史）、本人检测报告、复诊安排。**权限校验在工具内部**：编排层不可能知道模型下一轮会编出哪个 `patient_id`，唯一可靠的拦截点就是参数被消费的地方。
- **原生 function calling**（没有引入 LangGraph/LangChain）。编排是四个普通函数 —— `planner → tools → reflect → responder` —— 加一个驱动器。节点签名是 `f(state, client) -> 下一节点名`，将来要换成图编排只需新增一个文件，节点本身不用改。
- **护栏**：迭代上限、工具调用总数上限、以及一个会逐次收窄的墙钟预算（每次调用的超时取 `min(单次上限, 剩余预算)`）。模型若陷进"反复调工具"，会被毫秒级截断而不是挂死。
- **三层上下文压缩**：最近若干轮原文 + 中段摘要 + 更早的要点列表，**水位线存在 Redis 里**，让 worker 与 API 进程对"已经压到哪"有一致认识。剩余时间预算不够做摘要时，这一轮干脆不压。
- **执行轨迹**回传前端并落库：界面能展示答案是怎么来的，验收脚本也能对它断言。

### 3. 异步流水线（Celery + Redis）

训练与文档入库都搬离了请求路径。

- 入库原本是同步的：一份 200 切片的文档会占住上传请求约 30 秒。现在端点返回 `202` 与一行 `pending`，worker 再往里填内容。
- **停止是跨进程的**：停止标志存 Redis，因此在 API 进程点"停止训练"能真正传到 worker。
- **启动时回收中断任务**：worker 被杀之后，训练行会永远停在 `running`（医生看不到，也永远不能再训练）。
- **患者记录在医生保存后自动重新切片**，并清理过期版本 —— 哈希里含 `updated_at`，只重算不清理会让同一个病历在索引里留下新旧两版。

### 4. 评测体系

`backend/eval/` 里是一套可复现的对比，而不只是一个脚本：

- **52 条评测集**（知识问答 / 多步推理 / 多轮对话 / 安全 / 库外问题）。参考答案与标注切片**由语料解析并校验** —— 校验会断言 ground truth 与标注切片有足够长的公共子串，避免参考答案与原始资料脱节。
- **四组检索配置**复用同一次 `retrieve()` 调用（通道开关是新增的可选参数，默认路径行为不变）。
- **生成类指标**：幻觉率（LLM 裁判，参照物是**模型本次实际收到的上下文**）、引用合法性（确定性判据，专抓伪造的引用编号）、引用命中率、库外问题的拒答率。
- `--from-json` 能用已保存的结果重算指标 —— 调整口径不必再花几小时重新推理。

### 5. 安全与多租户隔离

- **JWT 认证** + 一次性验证码。过渡期的 `X-Username` 请求头兜底已移除（它曾让 `curl -H "X-Username: admin"` 直接冒充任何人），同时清掉了另外五处直接读该请求头的地方 —— 其中一处甚至把它当作**数据过滤键**。
- **患者数据隔离是结构性的、不是约定性的**：检索只接受 `RetrievalScope`，其 `patient_id` 谓词只有一个构造点，且 fail-closed（要求个人切片却没给患者 id 时直接抛异常，而不是返回所有人的病历）。
- **分层限流**：分钟级限流防突发，加上单会话与单日额度控成本。两者用**不同的错误码**，因为"太快了"与"用完了"该有不同的客户端行为。
- 完整的操作审计（操作人取自已认证身份）。

---

## 架构

```
                        ┌──────────────── Vue 3 SPA ────────────────┐
                        └──────────────────┬───────────────────────┘
                                           │ REST / JWT
   ┌───────────────────────────────────────▼───────────────────────────────────┐
   │  Flask API（10 个蓝图，100+ 接口）                                          │
   │  api/  →  services/  →  core/        认证 · 限流 · 额度 · 审计              │
   └───────┬─────────────────────────┬───────────────────────┬─────────────────┘
           │                         │                       │
     ┌─────▼──────┐          ┌───────▼────────┐      ┌───────▼─────────┐
     │ PostgreSQL │          │ Redis          │      │ Celery worker   │
     │ + pgvector │          │ 缓存·broker·标志 │      │ 训练 / 入库      │
     │  (HNSW)    │          │ ·额度           │      └───────┬─────────┘
     └────────────┘          └────────────────┘              │
                                                             │
   ┌─────────────────────────────────────────────────────────▼───────────────┐
   │  AI 层：LLM 接入（4 个 provider、支持工具调用）· RAG 管线 ·              │
   │         Agent 运行时 · YOLO 检测 · bge-m3 嵌入与重排                     │
   └─────────────────────────────────────────────────────────────────────────┘
```

### 项目结构

| 路径 | 内容 |
|---|---|
| `backend/api/` | 10 个蓝图：认证 / 患者 / 医生 / 管理员 / 检测 / 训练 / 知识库 / AI / 消息 / 分析 |
| `backend/services/rag/` | 入库管线、混合检索器、嵌入与重排单例、提示词契约 |
| `backend/services/agent/` | 工具注册表、身份与权限解析、编排器、提示词、记忆压缩 |
| `backend/services/llm_client.py` | 与 provider 无关的 LLM 客户端（OpenAI / ModelScope / 自定义 / 本地），含重试与工具调用 |
| `backend/core/` | 认证、限流、额度、缓存、任务回收、校验、安全过滤 |
| `backend/tasks/` | Celery 应用与训练 / 入库任务 |
| `backend/eval/` | 评测集、生成器与对比驱动 |
| `backend/scripts/` | 8 套验收脚本 + 四个常驻组件的运维脚本 |
| `frontend/` | Vue 3 + Element Plus 单页应用（存在，但不是当前工作重心） |
| `AI/` | 可选的本地模型服务（Qwen3-VL-4B）；不起它平台照常工作 |

---

## 快速开始

**环境要求**：Python 3.11、PostgreSQL 16（含 pgvector）、Redis、Node 22+（仅前端）。GPU 可选 —— 检测与嵌入都会退回 CPU。

```bash
git clone https://github.com/rauki34/BoneAIdetect.git
cd BoneAIdetect
python -m venv venv && venv/Scripts/activate      # Linux/macOS: source venv/bin/activate
pip install -r backend/requirements.txt            # 含 torch 与 ultralytics（下载数 GB，视平台而定）
cp backend/.env.example backend/.env               # 填 SECRET_KEY / JWT_SECRET_KEY / DATABASE_URL
```

拉起四个常驻组件（它们都不是 Windows 服务，重启电脑后要手动再起）：

```bash
bash backend/scripts/pg.sh start        # 1. PostgreSQL（含 pgvector）
bash backend/scripts/redis.sh start     # 2. Redis（缓存 + broker + 停止标志）
bash backend/scripts/flask.sh start     # 3. 后端 :5000（加 debug 参数可开详细日志）
bash backend/scripts/celery.sh start    # 4. Celery worker —— 训练与入库都在这里跑
```

> **worker 是独立进程。** 只起后端的话，训练与入库任务会一直躺在队列里：接口返回 `202 已受理`，任务永远停在"处理中"。四个脚本都支持 `stop` / `status` / `log`。

建知识库索引（首次运行会下载 bge-m3，约 2.2 GB）：

```bash
cd backend
python scripts/ingest_knowledge.py                 # 试运行：只报告将入库多少切片
python scripts/ingest_knowledge.py --apply         # 实际入库
```

界面：`cd frontend && npm install && npm run dev`。

`AI/` 本地模型服务是可选的 —— 不起它平台照常工作（在设置里改选远程提供商即可）。要跑它：`cd AI && pip install -r requirements.txt && python app.py`，监听 `:8000`。配置细节见 `AI服务配置说明.md`。

---

## 验证

以下都在真实运行的环境上执行。每套脚本都会打印 `通过 / 失败 / 跳过`，失败时退出码非零。

```bash
cd backend
python -m pytest tests -q                                       # 85 条，约 6 秒，不依赖模型

python scripts/verify_auth_flow.py logs/app.log                 # 21  认证、验证码、角色隔离
python scripts/verify_knowledge_api.py logs/app.log             # 23  知识库接口契约
python scripts/verify_knowledge_base.py --with-models           # 37  检索质量 + 越权泄漏
python scripts/verify_agent.py logs/app.log                     # 110 Agent 工具层与护栏（离线）
python scripts/verify_agent.py logs/app.log --with-llm          # 129（比离线多 19 条：接真实 LLM 的端到端）
python scripts/verify_queue.py                                  # 13  队列语义
python scripts/verify_patient_ingest.py logs/app.log            # 11  病历 → 索引的生命周期
python scripts/verify_quota.py logs/app.log                     # 22  额度与其错误契约
python scripts/smoke_training_queue.py                          # 18  训练全链路
```

单元测试层钉的是"不许回归"的契约 —— 其中包括一条**结构性证据**：新增工具调用能力后，既有 `chat()` 发出的请求体逐字段未变（用真实的请求构造器断言，而不是靠"跑一遍没报错"推断）。

静态检查：`ruff check .`（后端）与 `npx eslint src`（前端，仅警告）。两者与单元测试一起进 CI；CI 的依赖清单**刻意不装 torch**，因此依赖模型的验收套件留在本地跑。

---

## 已知边界

写出来而不是含糊带过：

- **Docker Compose 已提供，但未端到端跑通。** `docker compose config` 能过（schema、变量插值、卷都正确），但开发机上引擎起不来 —— 缺的是 WSL2 所需的 Windows 功能（VBS 已占用 hypervisor），不是硬件限制。compose 文件顶部写了剩下的步骤。
- **生成类指标只做过小样本验证**（每组 3 题）。上面的检索表是完整的；幻觉率/引用那组对比需要把 32 条知识问答全跑完（数小时），尚未产出。
- **Agent 偶尔会无据作答。** 当所有工具都返回 `not_found` 时，模型有时仍凭记忆作答。这是**被缓解而非被消除**：编排层会把这类轮次标成 `no_grounding`，让前端能告诉用户"本次回答没有检索到资料支撑"。
- **前端只做了部分重构** —— 三个视图组件仍然很大，图表渲染没有自动化测试。
- **表结构靠增量加列**（`create_all` + 显式的加列清单），不是 Alembic 迁移。
- **评测集对语料的覆盖很窄** —— 794 个共享切片里只标注了 32 个。

---

## 许可

[AGPL-3.0](LICENSE)。
