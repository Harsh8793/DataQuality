# DataPilot AI — System Architecture (as built)

> **Enterprise AI Copilot for Data Quality, Analytics & Governance**
>
> **Context:** Enterprise AI Hackathon · **Team:** 2 · **Orchestration:** Custom lightweight multi-agent

This document describes **the system as it exists in the code**: real folder layout,
real database tables, real API surface, real agent wiring — including the parts that
were built but are not wired up, which are marked as such rather than omitted.

For the agent-design submission view (node diagram, state management, HITL gate,
tool registry, memory strategy) see [`docs/architecture.md`](docs/architecture.md).
Section 11 records where the shipped system differs from the original 48-hour plan.

---

## 0. Guiding principles

1. **Deterministic core, AI garnish.** Profiling, quality checks, scoring, cleaning
   and SQL execution run in Pandas/DuckDB — fast, free, repeatable. The LLM only
   *explains, narrates, plans and classifies* on top. The product therefore works
   with the LLM switched off, which is why every AI path has a deterministic fallback.
2. **Refuse rather than guess.** When a question can't be answered from the data, the
   agent says so and names the real columns. Every number it states must be traceable
   to a query result (§5.5).
3. **Rules stay authoritative where correctness matters.** PII detection,
   classification and quality scoring are rule-based; the LLM can add prose but
   cannot override a rule's finding.
4. **`dataset_id` is the universal handle.** Every service, agent and endpoint keys
   off it.
5. **Disclose coverage.** Row caps, null exclusions, `Other` buckets and unparsed
   dates are stated in the answer rather than silently applied.

---

## 1. System architecture

### 1.1 Container view

```
┌───────────────────────────────────────────────────────────────────────────┐
│                            BROWSER (React SPA)                            │
│  React 18 · Vite 6 · TypeScript · Tailwind · TanStack Query · Recharts    │
└────────────────────────────────┬──────────────────────────────────────────┘
                                 │  REST / JSON  (JWT bearer)
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                        FASTAPI BACKEND (Python 3.12)                      │
│                                                                           │
│  ┌───────────────┐    ┌──────────────────────────────────────────────┐    │
│  │  API routers  │───▶│                SERVICE LAYER                 │    │
│  │ (thin, HTTP)  │    │  Dataset · Analysis · Cleaning · Chat · AI ·  │    │
│  │  app/api/v1   │    │  Dashboard · Governance · Edit · Report ·     │    │
│  └───────────────┘    │  CustomValidation · History · System · Auth   │    │
│                       └──────────────┬───────────────────────────────┘    │
│                                      ▼                                    │
│  ┌──────────────────────────────────────────────────────────────────┐     │
│  │              AGENT LAYER (app/agents, custom coordinator)         │     │
│  │  SimpleCoordinator pipeline:  Profiling → Quality → Governance    │     │
│  │  Called directly by services: Chat · Insight · Dashboard · Upload │     │
│  └────────┬──────────────────────────────┬──────────────────────────┘     │
│           ▼                              ▼                                │
│  ┌────────────────────┐   ┌──────────────────┐   ┌────────────────────┐   │
│  │  DETERMINISTIC     │   │    AI LAYER      │   │    PERSISTENCE     │   │
│  │  core/engines:     │   │  core/llm:       │   │  SQLite (metadata) │   │
│  │  loader profiler   │   │  groq_client.py  │   │  Parquet (the data)│   │
│  │  quality_checks    │   │  prompts.py      │   │  FS (uploads,      │   │
│  │  scorer cleaner    │   │  (no LangChain)  │   │      reports)      │   │
│  │  fixer affected    │   └────────┬─────────┘   └────────────────────┘   │
│  │  duckdb_engine     │            │                                      │
│  │  chart_recommender │            │                                      │
│  │  explanations      │            │                                      │
│  └────────────────────┘            │                                      │
└────────────────────────────────────┼──────────────────────────────────────┘
                                     ▼
                            ┌──────────────────┐
                            │     Groq API     │  llama-3.1-8b-instant
                            │  (external LLM)  │  (GROQ_MODEL, overridable)
                            └──────────────────┘
```

Repository layout at the top level:

```
Hackathon2026/
├── backend/     FastAPI app, tests, sample generators
├── frontend/    React SPA
├── docs/        agent-design doc + diagrams
├── Makefile     make backend / frontend / seed / clean
├── docker-compose.yml, render.yaml
└── README.md · ARCHITECTURE.md · DEPLOY.md
```

### 1.2 Architectural decisions

| # | Decision | Why | Status |
|---|----------|-----|--------|
| ADR-1 | **DuckDB over the in-memory DataFrame** for all chat SQL | Real SQL, zero setup, in-process, fast on wide tables | in use |
| ADR-2 | **Deterministic engines compute; the LLM narrates** | Reliability and zero cost for core metrics; survives an LLM outage | in use |
| ADR-3 | **Custom coordinator, not CrewAI/LangGraph** | Fastest to build and debug; the `Coordinator` protocol in `orchestrator.py` leaves room to swap | in use |
| ADR-4 | **Data persisted as Parquet on disk; metadata in SQLite** | Small DB, fast reload, columnar for DuckDB; the original upload is kept for provenance | in use |
| ADR-5 | **Read-only SQL, validated then row-capped** | `DuckDBEngine.validate` allows only single-statement `SELECT`/`WITH`, rejects DDL/DML, and injects `LIMIT 1000` | in use |
| ADR-6 | **LLM output is schema-validated or discarded** | `complete_json` parses and type-checks; unusable replies fall back to a deterministic plan | in use |
| ADR-7 | **Numeric grounding guard on every narrated answer** | Any figure not traceable to the result set is rejected and replaced with a computed sentence (§5.5) | in use |
| ADR-8 | **Rules own PII and classification; the LLM only adds prose** | Small models flag everything or nothing; `GovernanceAgent` merges LLM text without letting it change `is_pii` | in use |
| ADR-9 | **SSE for analysis progress** | `GET /analyze/stream` emits `progress`/`done` frames | **built, not consumed** — the UI calls the synchronous `POST /analyze` |
| ADR-10 | **No vector store, no LangChain** | Nothing in the product needs retrieval; the schema and a 3-row sample fit in one prompt | dropped from the plan |

### 1.3 Request lifecycle (upload → analyze)

```
POST /api/v1/datasets            (multipart)
  → UploadAgent + Loader: detect format/encoding/delimiter, load to DataFrame
  → store Parquet + original file, insert `uploaded_files` + `datasets` rows
  → returns dataset_id + summary

POST /api/v1/datasets/{id}/analyze
  → AnalysisService builds an AgentContext (df + dataset row)
  → SimpleCoordinator runs, isolating per-agent failures:
       ProfilingAgent   → 15 semantic types, per-column stats      (deterministic)
       QualityAgent     → 20 checks + 6-dimension score            (deterministic)
       GovernanceAgent  → PII/classification/tier (rules), LLM adds
                          business names + descriptions
  → persists quality_reports, quality_issues, dataset_columns, governance_reports
  → returns the full report

Per-issue explanations come from core/engines/explanations.py (deterministic,
column- and count-specific, zero tokens) — not from the LLM.
```

---

## 2. Folder structure (actual)

```
backend/
├── main.py                      ← uvicorn entrypoint (reload in dev)
├── requirements.txt             ← single pinned list (app + test + eval deps)
├── app/
│   ├── main.py                  ← app factory, middleware, CORS, exception handlers
│   ├── api/
│   │   ├── router.py            ← aggregates the v1 routers
│   │   └── v1/  auth · upload · analysis · chat · dashboard · governance
│   │             edits · reports · ai · history · system
│   ├── services/                ← business logic (13 services + base.py)
│   │   dataset · analysis · cleaning · chat · dashboard · governance · edit
│   │   report · ai · custom_validation · history · system · auth
│   ├── agents/                  ← agent layer
│   │   base.py                  ← Agent ABC, AgentContext, AgentResult
│   │   orchestrator.py          ← SimpleCoordinator (Profiling→Quality→Governance)
│   │   upload · profiling · quality · governance · chat · insight · dashboard
│   │   sql_agent.py             ← ⚠ implemented, no callers
│   │   cleaning_agent.py        ← ⚠ implemented, no callers
│   ├── core/
│   │   ├── engines/             ← deterministic compute (NO LLM in here)
│   │   │   loader · profiler · quality_checks · scorer · cleaner · fixer
│   │   │   affected · duckdb_engine · chart_recommender · explanations
│   │   ├── llm/  groq_client.py · prompts.py   ← all prompts in one module
│   │   ├── security.py · storage.py · logging.py
│   ├── models/                  ← 12 SQLAlchemy model modules → 19 tables
│   ├── repositories/            ← 11 repositories + base.py (DB access only)
│   ├── schemas/                 ← Pydantic: ai · auth · chat · common · dataset
│   │                              quality · system
│   ├── database/                ← session.py · base.py · init_db.py
│   ├── config/settings.py       ← pydantic-settings, env-driven
│   ├── constants/enums.py · dependencies/auth.py · exceptions/ · middleware/
│   └── validators/patterns.py   ← email/phone/url/date/zip/currency matchers
├── tests/                       ← 11 suites, offline (LLM stubbed) + 1 judge suite
├── scripts/                     ← sample generation + demo seeding
└── samples/                     ← generated demo datasets

frontend/src/
├── App.tsx                      ← routes: / · /upload · /datasets · /datasets/:id
├── layouts/AppShell.tsx         ← sidebar (Dashboard · Upload · Datasets) + topbar
├── pages/                       ← Home · UploadPage · Datasets · DatasetDetail · Login
├── components/
│   ├── dataset/OverviewPanel · CompareDatasetsModal
│   ├── quality/QualityPanel · ScoreGauge · AddValidationCard
│   ├── edit/EditPanel · cleaning/CleaningPanel (hidden)
│   ├── dashboard/DashboardPanel · charts/ChartRenderer · charts/KpiCard
│   ├── chat/ChatPanel · insights/InsightsPanel (hidden)
│   ├── governance/GovernancePanel · reports/ReportsPanel
│   ├── common/  DataTable · Modal · ConfirmDialog · CollapsibleCard · InfoTip
│   │            ApprovalBadge
│   └── ui/      badge · button · card · input · tabs · misc
├── services/                    ← one module per API area (8)
├── hooks/  useDatasets · useSystem   ·   contexts/AuthContext
└── types/  api.ts · models.ts
```

**Layering rule that holds throughout:** nothing imports upward. Engines never
import services; services never import routers; agents never import repositories.
Two exceptions worth knowing: `api/v1/dashboard.py` defines a small
`_InsightRunner(BaseService)` inline (it belongs in `services/`), and
`dependencies/auth.py` reaches into `repositories/` directly.

---

## 3. Database schema (SQLite via SQLAlchemy, 19 tables)

Metadata lives in SQLite; **the data itself lives in Parquet on disk**, referenced by
`datasets.parquet_path`. Integer surrogate keys throughout.

Every table inherits audit columns from the shared base:
`id`, `created_at`, `updated_at`, `created_by`, `updated_by`, `is_deleted`.
Only the domain columns are listed below.

```sql
users(email UNIQUE, name, password_hash, role)

uploaded_files(user_id→users, original_filename, stored_filename,
               extension, size_bytes, storage_path)

datasets(user_id→users, uploaded_file_id→uploaded_files,
         parent_id→datasets,           -- set when this row is a CLEANED version
         name, file_format, encoding, delimiter,
         row_count, col_count, file_size_bytes, memory_bytes,
         parquet_path, status, is_cleaned, story,
         approval_status, approval_note, reviewed_by, reviewed_at)   -- HITL gate

dataset_columns(dataset_id→datasets, name, ordinal,
                physical_type, semantic_type,
                null_count, null_pct, distinct_count, cardinality_ratio,
                min_val, max_val, mean_val, std_val, sample_values JSON,
                business_name, description, sensitivity, is_pii, owner)

-- Quality
quality_reports(dataset_id→, user_id→, overall_score,
                completeness, accuracy, consistency, uniqueness, validity, integrity,
                duplicate_rows, total_issues, duration_ms)
quality_issues(report_id→quality_reports, column_name, check_key, dimension,
               severity, count, sample JSON,
               problem, why, business_impact, recommended_fix, confidence)
issue_exclusions(dataset_id→, user_id→, check_key, column_name)
custom_validations(dataset_id→, user_id→, name, description,
                   dimension, severity, condition, is_active)

-- Fixes (batched so "undo all" and per-fix undo both work)
fix_batches(dataset_id→, user_id→, snapshot_path, row_count_before)
issue_fixes(batch_id→fix_batches, dataset_id→, check_key, column_name,
            identifier_column, severity, problem, op, rows_affected,
            detail, changes JSON)

-- Cleaning, edits, governance
cleaning_reports(dataset_id→, user_id→, cleaned_dataset_id→datasets,
                 operations JSON, comparison JSON, before_score, after_score)
dataset_edits(dataset_id→, user_id→, edits JSON, row_count)
governance_reports(dataset_id→, user_id→, classification, pii_columns JSON,
                   rationale, ingestion_tier, tier_rationale)

-- Chat, dashboards, activity
chat_history(user_id→, dataset_id→, title)              -- a session
chat_messages(session_id→chat_history, role, content,
              generated_sql, result_preview JSON, chart_spec JSON)
dashboard_history(user_id→, dataset_id→, spec JSON)     -- saved widget selection
analysis_history(user_id→, dataset_id→, action, summary, payload JSON)
generated_reports(user_id→, dataset_id→, report_type, title, file_path, size_bytes)
system_logs(level, source, message, context JSON)
```

**Relationships:** `users 1─* datasets 1─* dataset_columns`;
`datasets 1─* quality_reports 1─* quality_issues`;
`datasets 1─* governance_reports`;
`datasets 1─* chat_history 1─* chat_messages`;
`fix_batches 1─* issue_fixes`; cleaned datasets link back via `parent_id`.

**Migrations:** `database/init_db.py` runs `create_all()` plus a small additive
`ALTER TABLE` shim for columns added after the first release. It is SQLite-flavoured —
moving to another engine means replacing it with Alembic.

---

## 4. API surface (51 routes, prefix `/api/v1`)

JWT bearer auth on everything except `/auth/login`, `/auth/register` and
`/system/llm`. All responses are wrapped in
`{success, message, data, errors, timestamp}`.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/auth/register` · `/auth/login` | Create user · issue JWT |
| GET | `/auth/me` | Current user |
| **Datasets** | | |
| POST · GET | `/datasets` | Upload (multipart) · list |
| GET · DELETE | `/datasets/{id}` | Summary · delete |
| GET | `/datasets/{id}/preview` | First N rows |
| POST | `/datasets/{id}/rows/query` | Paged/filtered row query |
| POST | `/datasets/compare` | Two-dataset comparison |
| GET | `/datasets/{id}/export` | Current data as CSV (fixes + edits applied) |
| **Analysis** | | |
| POST | `/datasets/{id}/analyze` | Run the pipeline, return the report |
| GET | `/datasets/{id}/analyze/stream` | Same, streaming progress (SSE) — unused by the UI |
| GET | `/datasets/{id}/profile` · `/quality` · `/governance` | Stored results |
| POST | `/datasets/{id}/approval` | HITL approve/reject gate |
| **Quality fixes** | | |
| POST | `/datasets/{id}/quality/issues/{issue_id}/fix` · `/quality/fix-all` | Fix one · fix all |
| GET | `/datasets/{id}/quality/issues/{issue_id}/affected` | Rows an issue affects |
| GET | `/datasets/{id}/quality/fixes` | Applied-fix log |
| POST | `/datasets/{id}/quality/fixes/undo` · `/fixes/{fix_id}/undo` | Undo all · undo one |
| GET · POST · POST | `/datasets/{id}/quality/exclusions` (+`/remove`) | Ignore an issue |
| GET · POST · DELETE | `/datasets/{id}/quality/validations` (+`/{id}`) | Custom rules |
| POST | `/datasets/{id}/quality/validations/propose` | English → proposed rule (LLM) |
| **Cleaning & edits** | | |
| GET · POST | `/datasets/{id}/clean` | Proposed ops · apply |
| GET | `/datasets/{id}/clean/download` · `/clean/operations/{i}/affected` | Cleaned file · impact |
| GET · POST · POST | `/datasets/{id}/edits` (+`/undo`) | Manual cell edits |
| **Chat** | | |
| POST | `/datasets/{id}/chat` | Question → SQL → table + chart + answer |
| GET · DELETE | `/datasets/{id}/chat/history` | Conversation · clear |
| GET | `/datasets/{id}/chat/suggestions` | Starter questions from the profile |
| **Dashboard & AI** | | |
| GET · PUT | `/datasets/{id}/dashboard` | Widget pool + selection · save selection |
| POST | `/datasets/{id}/dashboard/command` | Sentence → proposed KPI/chart |
| GET | `/datasets/{id}/insights` · `/story` | Business insights · executive summary |
| POST | `/datasets/{id}/explain` | "Explain this" for a widget |
| **Reports & system** | | |
| POST | `/datasets/{id}/reports` | Generate PDF/Excel/JSON/CSV |
| GET | `/reports/{report_id}/download` | Download an artifact |
| GET | `/history` | Activity feed — **backend only, no UI consumer** |
| GET | `/system/llm` | LLM health (status, model, last success/failure) |

---

## 5. Agent design

### 5.1 Contract

```python
@dataclass
class AgentContext:                 # threaded through a pipeline, enriched in place
    dataset_id: str; dataset_name: str; df: pd.DataFrame
    profile: DatasetProfile | None; findings: list[QualityFinding]
    score: QualityScore | None; meta: dict          # + emit() for progress events

@dataclass
class AgentResult:
    agent: str; ok: bool; data: Any = None; error: str | None = None

class Agent(ABC):
    name: str
    def run(self, ctx: AgentContext) -> AgentResult: ...
```

Every agent returns the same envelope, so one failing agent degrades its own step
and nothing else. `SimpleCoordinator` catches exceptions per agent and still emits
`done`.

### 5.2 Agents

| Agent | Wiring | Responsibility |
|-------|--------|----------------|
| `UploadAgent` | `DatasetService` | Format/encoding/delimiter detection, load, persist |
| `ProfilingAgent` | pipeline | Wraps `Profiler`: 15 semantic types + per-column stats |
| `QualityAgent` | pipeline | Wraps `QualityEngine` + `Scorer`: 20 checks, 6 dimensions |
| `GovernanceAgent` | pipeline | PII/classification/tier by rules; LLM adds business names in batches of 20 with retry-by-halving |
| `ChatAgent` | `ChatService` | Plans (converse vs. SQL vs. insights), generates SQL, executes, guards, narrates, builds the chart spec |
| `InsightAgent` | `ChatService`, `api/v1/dashboard` | Business insights (LLM) with a profile-derived fallback |
| `DashboardAgent` | `DashboardService` | Wraps `ChartRecommender` — **no LLM** |
| `SqlAgent` | — | ⚠ Implemented, no callers: `ChatAgent` does its own NL→SQL |
| `CleaningAgent` | — | ⚠ Implemented, no callers: `CleaningService` uses `Cleaner` directly |

`InsightAgent.explain_issues()` is also unreferenced — per-issue explanations are
served by the deterministic `core/engines/explanations.py`, which injects the real
column and count instead of one generic sentence per check type.

### 5.3 Pipeline

```
SimpleCoordinator.run_analysis(ctx):
    ProfilingAgent → QualityAgent → GovernanceAgent
    (each wrapped in try/except; progress emitted via ctx.emit)
```

`InsightAgent` is deliberately **excluded** from the pipeline: analysis re-runs after
every fix and edit, and insights are generated on demand by the Insights tab, so
keeping it out makes analysis fast and token-free.

### 5.4 Chat flow

```
POST /datasets/{id}/chat  "average revenue by region"
  1. Shortcuts:  insight-style asks → InsightAgent; whole-dataset row counts → COUNT(*)
  2. Plan (LLM):  schema + 3 sample rows + last 8 turns → {"mode":"sql"|"answer", ...}
                  unusable / deflecting plans fall back to a deterministic pattern planner
  3. Rewrite:     wrong aggregate corrected to the one asked for;
                  text equality filters made case/whitespace-insensitive
  4. Execute:     DuckDBEngine.validate → run on the DataFrame (dates pre-parsed)
                  failure → retry once with the deterministic fallback SQL
  5. Narrate (LLM): question + row count + FIRST 10 result rows only
  6. Guard:       every number in the reply must be traceable to the result,
                  else replace with a computed sentence
  7. Disclose:    notes for dropped filters, spelling variants, truncation, unparsed dates
  8. Chart:       2-column results → {type, title, x, y, x_label, y_label, data}
```

### 5.5 What the LLM actually receives

The full dataset is never sent. Per call:

| Call | Payload |
|------|---------|
| Chat planner | Column names + types, **3 sample rows** (≤1500 chars), last 8 turns (200 chars each), the question |
| Chat narrator | The question, the true row count, and the **first 10 result rows** (≤1200 chars) |
| Dashboard command | Schema string + the user's sentence — **no rows** |
| Insights / story | Profile summary (names, types, score) — **no rows** |
| Governance | Column names, types and 2 sample values per column, batched 20 at a time |
| Widget explain | The widget spec and row/column counts — **no rows** |

A million-row average is aggregated locally by DuckDB; only the resulting numbers
travel. The one place real data leaves the machine is those 3 sample rows in the chat
planner — the place to mask if a column holds PII.

---

## 6. Frontend architecture

```
AppShell (sidebar: Dashboard · Upload · Datasets)
└── /datasets/:id → DatasetDetail
      ├── Overview     OverviewPanel      profile, semantic types, AI column docs, story
      ├── Quality      QualityPanel       score gauge, issues, fix/undo, AddValidationCard
      ├── Edit data    EditPanel          cell edits + undo history
      ├── Dashboard    DashboardPanel     KPI/chart pool, propose-and-approve widgets
      ├── Chat         ChatPanel          question → SQL + table + ChartRenderer
      ├── Governance   GovernancePanel    classification, PII, Bronze/Silver/Gold
      └── Reports      ReportsPanel       PDF/Excel/JSON/CSV export
      (hidden behind comments: Cleaning, Insights — panels exist and work)
```

- **Data fetching:** TanStack Query per panel; `lib/apiClient.ts` unwraps the
  `ApiResponse` envelope and attaches the JWT. No global store — server state is the
  source of truth.
- **Charts:** Recharts. The backend sends a spec (`type`, `x`, `y`, `x_label`,
  `y_label`, `data`, `meta`); `ChartRenderer` maps it to a chart. Axis captions come
  from the spec because they carry the aggregation — "Total revenue" versus "Average
  revenue" is not recoverable from the data keys.
- **Auth:** `AuthContext` + `ProtectedRoute`; token in `localStorage`.

---

## 7. Quality checks (engine registry)

20 deterministic checks in `core/engines/quality_checks.py`, plus any user-defined
rules from `custom_validations`:

`missing_values` · `blank_strings` · `whitespace` · `duplicate_rows` ·
`duplicate_ids` · `duplicate_columns` · `invalid_email` · `invalid_phone` ·
`invalid_url` · `invalid_date` · `negative_values` · `outliers` ·
`case_inconsistency` · `mixed_types` · `datatype_mismatch` · `constant_column` ·
`high_cardinality` · `low_cardinality` · `unicode_issues` · `empty_dataset`

Score = weighted mean of six dimensions (`core/engines/scorer.py`):

| Dimension | Weight |
|---|---|
| Completeness | 0.25 |
| Validity | 0.20 |
| Uniqueness | 0.15 |
| Consistency | 0.15 |
| Accuracy | 0.15 |
| Integrity | 0.10 |

Tier mapping (`GovernanceAgent`): score ≥ 90 **and** cleaned → Gold; ≥ 75 → Silver;
otherwise Bronze.

---

## 8. Testing

**452 tests, 89% backend coverage (5,799 statements), ~45s.** The suite never calls
Groq: an autouse fixture replaces the LLM singleton, so each tab is tested twice —
once with no model, once with a scripted one. Many tests are regressions against
wrong answers the product actually produced (a narrated count taken from a 10-row
preview, `MAX` reported as a total, an ISO date column typed as a phone number).

| Suite | Covers |
|---|---|
| `test_overview_tab.py` | loader, profiler, data story |
| `test_quality_tab.py` | the 20 checks, scorer, explanations, targeted fixes |
| `test_dashboard_tab.py` | chart builders, coverage/labels, 9 aggregations |
| `test_chat_tab.py` | SQL safety, number grounding, filter normalisation, narration |
| `test_governance_edit_reports_tabs.py` | classification, PII rules, report writers |
| `test_tab_service_flows.py` | end-to-end service flows per tab |
| `test_ai_and_validation_paths.py` · `test_llm_driven_paths.py` | AI paths, planner branches |
| `test_remaining_tab_paths.py` | per-issue fixes, per-fix undo, row filtering |
| `test_api.py` · `test_engines.py` | API + engine integration |
| `test_llm_judge_metrics.py` | DeepEval faithfulness / answer-relevancy / contextual precision+recall against the live model — **skipped unless `RUN_LLM_JUDGE=1`** (costs tokens, non-deterministic) |

---

## 9. Tech stack (pinned)

| Layer | Choice |
|---|---|
| Backend | FastAPI 0.115.6 · uvicorn 0.34.0 · Python 3.12 |
| Data | pandas 2.2.3 · DuckDB 1.1.3 · Parquet |
| DB | SQLAlchemy 2.0.36 · SQLite (engine-agnostic ORM; see §3 on migrations) |
| LLM | Groq SDK 0.15.0 · `llama-3.1-8b-instant` by default |
| Auth | python-jose 3.3.0 (JWT) · bcrypt |
| Export | reportlab 4.2.5 (PDF) · openpyxl 3.1.5 (Excel) |
| Validation | pydantic 2.13.4 · pydantic-settings |
| Frontend | React 18.3 · Vite 6 · TypeScript 5.7 · Tailwind 3.4 · TanStack Query 5.62 · Recharts 2.15 |
| Eval | pytest 9.1.1 · pytest-cov · deepeval 4.1.5 |

Backend dependencies live in a **single** `backend/requirements.txt` (app, test and
eval pinned together).

---

## 10. Known gaps

Honest list, kept here so nothing looks accidental:

1. **`SqlAgent` and `CleaningAgent` are unwired** — fully implemented, zero callers.
   Wire them or delete them.
2. **`InsightAgent.explain_issues()` + its 20-entry fallback table duplicate**
   `core/engines/explanations.py`. The engine version is better (it names the real
   column); the agent copy is dead.
3. **The `/history` endpoint has no UI consumer** — the global History tab was
   removed in favour of per-dataset activity (chat history, edit history).
4. **SSE analysis progress is built but unused** — the UI calls the synchronous
   `POST /analyze`.
5. **Semantic-type sets are declared in five places** (`chart_recommender`,
   `ai_service`, `dashboard_service`, and inline in `chat_agent` and `insight_agent`).
   Adding a type means editing all five.
6. **Insight prose has no numeric guard.** Chat answers are grounded (ADR-7); insight
   text is not, so a fabricated figure there would reach the user.
7. **`api/v1/dashboard.py` holds a service class**, and `dependencies/auth.py` skips
   the service layer — the only two layering exceptions.
8. **Cleaning and Insights tabs are commented out** in `DatasetDetail.tsx` while the
   panels remain functional.
9. **`requirements.txt` pins `python-pptx`, `lxml` and `xlsxwriter`**, which nothing
   imports — Excel export goes through `openpyxl`. Dropping them (and `deepeval`'s
   ~38 transitive packages) would cut a few hundred MB from the production image.

---

## 11. Deviations from the original 48-hour plan

The first version of this document was a delivery plan with priority tags and a task
backlog. What actually shipped differs as follows:

| Planned | Outcome |
|---|---|
| ChromaDB vector store, LangChain | **Not built.** No retrieval need; only a leftover `chroma_dir` setting remains |
| Compare view as a page | Shipped as `CompareDatasetsModal` + `POST /datasets/compare` |
| History page + `history_service` timeline UI | Backend shipped; **UI removed** (see gap 3) |
| Streaming chat tokens (SSE) | Chat is a single JSON response; SSE exists only for analysis progress |
| `Recommendations`, `/metadata`, `/chat/sessions` endpoints | Not built; column metadata is returned with the profile |
| Report agent | No agent; `ReportService` writes PDF/Excel/JSON/CSV directly |
| 6 services in the plan | 13 services shipped (fixes, edits, exclusions, custom validations, system health) |
| `llama-3.3-70b` | Runs on `llama-3.1-8b-instant`; the 70B model is used only as the eval judge |

Beyond the plan: per-fix undo with batch snapshots, an English→validation-rule
builder, a HITL approval gate on low-quality datasets, manual cell editing with undo,
propose-and-approve dashboard widgets, coverage disclosure on every chart, and the
numeric grounding guard.
