# Smart Orthopedics Cloud Platform

**English** | [中文](README.zh-CN.md)

A full-stack orthopedic diagnosis platform built around three AI capabilities: **YOLO-based fracture detection**, **hybrid RAG over a clinical corpus**, and a **tool-using agent** that assists patients through their recovery.

The engineering focus of this repository is the backend and the AI layer: a Flask service on PostgreSQL/pgvector + Redis + Celery, with a provider-agnostic LLM client, a hybrid retrieval pipeline, and an agent runtime that plans, calls tools, and keeps layered memory. (There is also a Vue 3 frontend — see [Project layout](#project-layout).)

---

## Highlights

### 1. Hybrid RAG with measured retrieval quality

Retrieval runs four stages: **pgvector HNSW** (bge-m3, 1024-d) and **BM25** (jieba-tokenised) in parallel, fused with **Reciprocal Rank Fusion**, then reordered by **bge-reranker-v2-m3**. Every answer carries citations back to the exact chunk (`index / doc / section / page / chunk_id / score`).

Measured on a 52-item evaluation set (see [Evaluation](#4-evaluation-harness)) — 32 knowledge questions plus 5 out-of-scope ones:

| Config | hit@1 | hit@5 | MRR | P50 latency |
|---|---|---|---|---|
| Vector only | 75.0% | 96.9% | 0.846 | 75 ms |
| Hybrid (no rerank) | 90.6% | 100.0% | 0.953 | 77 ms |
| Hybrid + rerank | 90.6% | 100.0% | 0.948 | 436 ms |

Two things this table says that a simpler A/B/C comparison would hide:

- **The ranking gain comes from BM25, not from the reranker.** Adding the cross-encoder costs ~6× latency for no ranking improvement (MRR even drops slightly). Running a fourth configuration is what made that visible.
- **The reranker's real contribution is a *calibrated relevance score*.** RRF scores are rank-based (`1/(60+rank)`), so "answerable" and "unanswerable" questions land in nearly the same band — a safety margin of **0.0003**, unusable as a threshold. After reranking the two bands separate by **0.80**, which is what makes the relevance gate in §2 possible at all.

### 2. Agent: tool use, planning, and layered memory

A patient-facing rehab assistant where the model decides *what to look up* rather than receiving pre-injected context.

- **5 read-only tools** — guideline search, own medical records, own profile (allergies/history), own detection reports, follow-up schedule. Permission checks live **inside** each tool: the orchestrator cannot know which `patient_id` the model will invent, so the only reliable interception point is where the argument is consumed.
- **Native function calling** (no LangGraph/LangChain). The orchestration is four plain functions — `planner → tools → reflect → responder` — driven by a loop. Node signatures are `f(state, client) -> next_node`, so swapping in a graph runtime later means adding a file, not rewriting the nodes.
- **Guardrails**: iteration cap, total tool-call cap, and a wall-clock budget that shrinks each call's timeout (`min(per-call limit, remaining budget)`). A model that loops on tool calls is cut off in milliseconds instead of hanging.
- **Layered context compression**: recent turns verbatim + a mid-range summary + an earlier bullet list, with a **watermark kept in Redis** so workers and API processes agree on what has already been compressed. Compression is skipped entirely when the remaining time budget is too small to summarise.
- **Execution trace** returned to the client and persisted, so the UI can show *how* an answer was reached — and so `verify_agent.py` can assert on it.

### 3. Asynchronous pipeline (Celery + Redis)

Training runs and document ingestion moved off the request path into Celery workers.

- Ingestion was synchronous: a 200-chunk document blocked the upload request for ~30 s. Now the endpoint returns `202` with a `pending` row and the worker fills it in.
- **Cancellation is cross-process**: stop flags live in Redis, so stopping a training job from the API process actually reaches the worker.
- **Stale-task recovery** on startup: a worker killed mid-training would otherwise leave rows stuck in `running` forever (invisible to doctors, and re-trainable never).
- Patient records are re-ingested automatically when a doctor creates or edits them, with older derived documents pruned — the hash includes `updated_at`, so recomputing without pruning would leave two conflicting versions of the same record in the index.

### 4. Evaluation harness

`backend/eval/` contains a reproducible comparison, not just a script:

- **52-item dataset** (knowledge / multi-step / multi-turn / safety / out-of-scope). Answers are **derived from the corpus and validated** — ground truth is checked to share a long substring with the labelled chunks, so the reference can't drift from the source material.
- **Four retrieval configurations** reusing one `retrieve()` call (channel switches are additive; the default path is unchanged).
- **Generation metrics** on a real LLM: hallucination rate (LLM-as-judge against *the context the model actually received*), citation validity (deterministic — catches fabricated reference numbers), citation hit rate, refusal rate on out-of-scope questions.
- `--from-json` recomputes metrics from a saved run, so adjusting a definition doesn't cost another few hours of inference.

### 5. Safety and multi-tenant isolation

- **JWT** auth with single-use captcha. The transitional `X-Username` header fallback was removed (it allowed `curl -H "X-Username: admin"` to impersonate anyone), along with five places that read it directly — including one that used it as a *data filter key*.
- **Patient data isolation is structural, not conventional**: retrieval accepts only a `RetrievalScope`, whose `patient_id` predicate has a single construction point and fails closed (asking for personal chunks without a patient id raises rather than returning everyone's records).
- **Layered limits**: per-minute rate limits for burst control, plus per-session and per-day quotas for cost control. The two use distinct error codes because "too fast" and "out of quota" warrant different client behaviour.
- Full audit log (who did what, resolved from the authenticated identity).

---

## Architecture

```
                        ┌──────────────── Vue 3 SPA ────────────────┐
                        └──────────────────┬───────────────────────┘
                                           │ REST / JWT
   ┌───────────────────────────────────────▼───────────────────────────────────┐
   │  Flask API (10 blueprints, 100+ endpoints)                                │
   │  api/  →  services/  →  core/            auth · rate limit · quota · audit │
   └───────┬─────────────────────────┬───────────────────────┬─────────────────┘
           │                         │                       │
     ┌─────▼──────┐          ┌───────▼────────┐      ┌───────▼─────────┐
     │ PostgreSQL │          │ Redis          │      │ Celery worker   │
     │ + pgvector │          │ cache · broker │      │ training/ingest │
     │  (HNSW)    │          │ flags · quota  │      └───────┬─────────┘
     └────────────┘          └────────────────┘              │
                                                             │
   ┌─────────────────────────────────────────────────────────▼───────────────┐
   │  AI layer: LLM client (4 providers, tool calling) · RAG pipeline ·      │
   │            agent runtime · YOLO detectors · bge-m3 embed + reranker     │
   └─────────────────────────────────────────────────────────────────────────┘
```

### Project layout

| Path | Contents |
|---|---|
| `backend/api/` | 10 blueprints — auth, patient, doctor, admin, detection, training, knowledge, ai, message, analysis |
| `backend/services/rag/` | Ingestion pipeline, hybrid retriever, embedder/reranker singletons, prompt contracts |
| `backend/services/agent/` | Tool registry, principal/permission resolution, orchestrator, prompts, memory compression |
| `backend/services/llm_client.py` | Provider-agnostic LLM client (OpenAI / ModelScope / custom / local) with retries and tool calling |
| `backend/core/` | Auth, rate limiting, quota, cache, recovery, validation, security filters |
| `backend/tasks/` | Celery app and the training / ingestion tasks |
| `backend/eval/` | Evaluation dataset, builder, and the comparison runner |
| `backend/scripts/` | 8 acceptance suites + operational scripts for the four runtime components |
| `frontend/` | Vue 3 + Element Plus SPA (present; not the focus of current work) |
| `AI/` | Optional local model service (Qwen3-VL-4B); the platform works without it |

---

## Getting started

**Requirements:** Python 3.11, PostgreSQL 16 with pgvector, Redis, Node 22+ (frontend only). A CUDA GPU is optional; detection and embedding fall back to CPU.

```bash
git clone https://github.com/rauki34/BoneAIdetect.git
cd BoneAIdetect
python -m venv venv && venv/Scripts/activate      # Linux/macOS: source venv/bin/activate
pip install -r backend/requirements.txt            # includes torch + ultralytics (multi-GB download)
cp backend/.env.example backend/.env               # then set SECRET_KEY / JWT_SECRET_KEY / DATABASE_URL
```

Start the four runtime components (none of them are registered services — a reboot means starting them again):

```bash
bash backend/scripts/pg.sh start        # 1. PostgreSQL (pgvector)
bash backend/scripts/redis.sh start     # 2. Redis (cache + broker + flags)
bash backend/scripts/flask.sh start     # 3. API on :5000  (add `debug` for verbose logs)
bash backend/scripts/celery.sh start    # 4. Celery worker — training & ingestion run here
```

> **The worker is a separate process.** Starting only the API leaves training and ingestion jobs queued forever: the endpoint returns `202 Accepted` and the task sits in "processing" indefinitely. Each script also supports `stop` / `status` / `log`.

Build the knowledge base (first run downloads bge-m3, ~2.2 GB):

```bash
cd backend
python scripts/ingest_knowledge.py                 # dry run — report what would be indexed
python scripts/ingest_knowledge.py --apply         # index the corpus
```

Then: `cd frontend && npm install && npm run dev` for the UI.

The `AI/` local model service is optional — the platform works without it (pick a remote provider in settings instead). To run it: `cd AI && pip install -r requirements.txt && python app.py`, which serves on `:8000`. Setup details are in `AI服务配置说明.md`.

---

## Verification

Everything below runs against a live stack. Suites are grouped by concern, and each one prints `passed / failed / skipped` with a non-zero exit code on failure.

```bash
cd backend
python -m pytest tests -q                                       # 85 tests, ~6 s, no models needed

python scripts/verify_auth_flow.py logs/app.log                 # 21  auth, captcha, role isolation
python scripts/verify_knowledge_api.py logs/app.log             # 23  knowledge API contract
python scripts/verify_knowledge_base.py --with-models           # 37  retrieval quality + leak tests
python scripts/verify_agent.py logs/app.log                     # 110 agent tools + guardrails (offline)
python scripts/verify_agent.py logs/app.log --with-llm          # 129 (+19: end-to-end vs a real LLM)
python scripts/verify_queue.py                                  # 13  queue semantics
python scripts/verify_patient_ingest.py logs/app.log            # 11  record → index lifecycle
python scripts/verify_quota.py logs/app.log                     # 22  quotas and their error contract
python scripts/smoke_training_queue.py                          # 18  training end-to-end
```

The unit-test layer covers contracts that must not regress — including a structural proof that adding tool calling did not change the existing `chat()` request payload (asserted field-by-field through the real request builder, not inferred from a passing run).

Static checks: `ruff check .` (backend) and `npx eslint src` (frontend, warnings only). Both run in CI alongside the unit tests; the CI install deliberately omits torch, so the model-dependent suites stay local.

---

## Known limitations

Written down rather than glossed over:

- **Docker Compose is provided but has not been run end-to-end.** `docker compose config` validates (schema, interpolation, volumes), but the engine will not start on the development machine — a Windows feature gap (WSL2 platform features absent while VBS already owns the hypervisor), not a hardware limitation. The compose file documents the remaining steps.
- **The evaluation's generation metrics have only been smoke-tested** (3 questions per config). The retrieval table above is complete; the hallucination/citation comparison needs a multi-hour run over all 32 knowledge questions and is not yet published.
- **The agent occasionally answers without grounding.** When every tool returns `not_found`, the model sometimes answers from parametric memory anyway. This is mitigated, not fixed: the orchestrator flags such turns (`no_grounding`) so the client can tell the user the answer has no retrieved support.
- **The frontend is only partly refactored** — three view components remain large, and chart rendering has no automated test.
- **Schema management is additive**, not migration-based: `create_all` plus an explicit "add column" list, rather than Alembic revisions.
- **Corpus coverage of the evaluation set is narrow** — 32 of 794 shared chunks are labelled.

---

## License

[AGPL-3.0](LICENSE).
