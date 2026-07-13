# DataPilot AI — System Architecture & Delivery Plan

> **Enterprise AI Copilot for Data Quality, Analytics & Governance**
>
> **Context:** Enterprise AI Hackathon · **Window:** 24–48h · **Team:** 2–3 · **Orchestration:** Custom lightweight multi-agent

---

## 0. Guiding Principles (read this first)

1. **Demo-first architecture.** Every decision optimizes for a jaw-dropping 5-minute demo that *looks* like a shipping commercial product. We build the full vision's *skeleton* but only flesh out the **critical path** (marked 🔴) in 48h.
2. **AI-first, not CRUD.** The differentiator is the multi-agent pipeline + "chat with your data" + AI explanations. That is where we spend our best hours.
3. **Deterministic core, AI garnish.** Profiling, quality checks, and cleaning are done in **Pandas/DuckDB deterministically** (fast, reliable, no API cost). The LLM *explains, narrates, and recommends* on top. This means the app works even if the Groq API is slow/down — critical for a live demo.
4. **One-command run.** `docker compose up` or a single `make dev`. Judges never see a stack trace.
5. **Fake nothing that's cheap to make real, mock anything that's expensive.** Real profiling/quality/cleaning/SQL. Mock/simplify: auth (local only), governance (rules + LLM), vector search (only if time).

### Priority legend
- 🔴 **Critical path** — must work in the demo. Build first.
- 🟡 **High value** — big "wow", build if core is stable.
- 🟢 **Stretch** — nice-to-have, only if ahead of schedule.

---

## 1. System Architecture

### 1.1 High-level (C4 Container view)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                             BROWSER (User)                                │
│  React + Vite + TS + Tailwind + shadcn/ui + TanStack Query + Recharts     │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 │  HTTPS / JSON (REST)  +  SSE (streaming AI)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        FASTAPI BACKEND (Python)                           │
│                                                                           │
│   ┌──────────────┐   ┌────────────────────────────────────────────────┐  │
│   │  API Routers │──▶│              SERVICE LAYER                       │  │
│   │ (thin, HTTP) │   │  DatasetService · ProfilingService ·            │  │
│   └──────────────┘   │  QualityService · CleaningService · ChatService │  │
│                      │  GovernanceService · ReportService · ...        │  │
│                      └───────────────┬────────────────────────────────┘  │
│                                      ▼                                     │
│   ┌───────────────────────────────────────────────────────────────────┐  │
│   │                 AGENT ORCHESTRATOR (custom)                         │  │
│   │  Coordinator dispatches to independent Agents (shared context)      │  │
│   │  Upload · Profiling · Quality · Cleaning · Governance ·             │  │
│   │  SQL · Dashboard · Insight · Report · Chat                          │  │
│   └───────┬───────────────────────┬───────────────────┬─────────────────┘  │
│           ▼                       ▼                   ▼                    │
│   ┌──────────────┐        ┌──────────────┐    ┌──────────────────┐        │
│   │  ANALYTICS   │        │   AI LAYER   │    │   PERSISTENCE    │        │
│   │  Pandas +    │        │ Groq (LLM) + │    │ SQLite (metadata)│        │
│   │  NumPy +     │        │ LangChain +  │    │ ChromaDB (vectors)│       │
│   │  DuckDB      │        │ prompt tmpls │    │ FS (parquet cache)│       │
│   └──────────────┘        └──────┬───────┘    └──────────────────┘        │
└──────────────────────────────────┼────────────────────────────────────────┘
                                    ▼
                          ┌──────────────────┐
                          │   Groq API       │  (external LLM inference)
                          │  llama-3.3-70b   │
                          └──────────────────┘
```

### 1.2 Key architectural decisions (ADRs, condensed)

| # | Decision | Why |
|---|----------|-----|
| ADR-1 | **DuckDB over the uploaded file** as the query engine for Chat/SQL | Zero-setup, in-process, blazing on CSV/Parquet, real SQL. Perfect for "chat with data". |
| ADR-2 | **Deterministic engines do the work; LLM narrates** | Reliability under demo pressure + no cost/latency for core metrics. |
| ADR-3 | **Custom agent orchestrator** (not CrewAI) | Fastest to build/debug in 48h; CrewAI hidden behind an `Orchestrator` interface so we *can* swap it as a stretch. |
| ADR-4 | **Persist datasets as Parquet** on disk, metadata in SQLite | Fast reload, small footprint, columnar for DuckDB. Original file kept for provenance. |
| ADR-5 | **SSE for AI streaming**, plain REST for everything else | ChatGPT-like token streaming = huge perceived quality. Simpler than websockets. |
| ADR-6 | **`dataset_id` is the universal handle** | Every agent/endpoint keys off it. Clean, RESTful, cache-friendly. |
| ADR-7 | **LLM output is always schema-validated (Pydantic)** | Structured, renderable AI results; retry on malformed JSON. No "wall of text". |

### 1.3 Request lifecycle (example: upload → analyze)

```
POST /datasets (file)
  → UploadAgent: detect encoding/delimiter/format, load to DataFrame, save Parquet, insert row in SQLite
  → returns dataset_id + summary
POST /datasets/{id}/analyze  (kicks off pipeline, streams progress via SSE)
  → ProfilingAgent  → column types, stats, semantic types  (deterministic)
  → QualityAgent    → 20+ checks, scores, severity          (deterministic)
  → GovernanceAgent → PII/sensitivity classification        (rules + LLM)
  → InsightAgent    → LLM narrates issues + business impact  (Groq, streamed)
  → persists AnalysisRun + Issues + Scores to SQLite
```

---

## 2. Folder Structure (production-grade)

```
datapilot-ai/
├── README.md
├── ARCHITECTURE.md                 ← this file
├── docker-compose.yml
├── Makefile                        ← make dev / make seed / make demo
│
├── backend/
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── .env.example                ← GROQ_API_KEY, DB_URL, etc.
│   ├── app/
│   │   ├── main.py                 ← FastAPI app factory, middleware, CORS
│   │   ├── config.py               ← pydantic-settings (env-driven)
│   │   ├── logging.py              ← structured logging setup
│   │   │
│   │   ├── api/                    ← THIN routers (HTTP only, no logic)
│   │   │   ├── deps.py             ← DI: get_db, get_current_user, services
│   │   │   ├── router.py           ← aggregates all v1 routers
│   │   │   └── v1/
│   │   │       ├── auth.py
│   │   │       ├── datasets.py
│   │   │       ├── profiling.py
│   │   │       ├── quality.py
│   │   │       ├── cleaning.py
│   │   │       ├── chat.py
│   │   │       ├── dashboard.py
│   │   │       ├── insights.py
│   │   │       ├── governance.py
│   │   │       ├── reports.py
│   │   │       ├── history.py
│   │   │       └── compare.py
│   │   │
│   │   ├── services/               ← business logic (orchestrates engines+agents)
│   │   │   ├── dataset_service.py
│   │   │   ├── profiling_service.py
│   │   │   ├── quality_service.py
│   │   │   ├── cleaning_service.py
│   │   │   ├── chat_service.py
│   │   │   ├── governance_service.py
│   │   │   ├── report_service.py
│   │   │   └── history_service.py
│   │   │
│   │   ├── agents/                 ← multi-agent layer
│   │   │   ├── base.py             ← Agent ABC (run(ctx)->result), AgentContext
│   │   │   ├── orchestrator.py     ← Coordinator, pipeline definition, SSE progress
│   │   │   ├── upload_agent.py
│   │   │   ├── profiling_agent.py
│   │   │   ├── quality_agent.py
│   │   │   ├── cleaning_agent.py
│   │   │   ├── governance_agent.py
│   │   │   ├── sql_agent.py
│   │   │   ├── dashboard_agent.py
│   │   │   ├── insight_agent.py
│   │   │   ├── report_agent.py
│   │   │   └── chat_agent.py
│   │   │
│   │   ├── engines/                ← deterministic compute (NO LLM here)
│   │   │   ├── loader.py           ← format/encoding/delimiter detection + load
│   │   │   ├── profiler.py         ← semantic type inference, stats
│   │   │   ├── quality_checks.py   ← the 20+ checks, each a pure function
│   │   │   ├── scorer.py           ← 6-dimension quality score
│   │   │   ├── cleaner.py          ← cleaning transforms (idempotent)
│   │   │   ├── duckdb_engine.py    ← query execution
│   │   │   └── chart_recommender.py← picks chart types from column semantics
│   │   │
│   │   ├── ai/                     ← LLM plumbing
│   │   │   ├── groq_client.py      ← thin wrapper, retry, streaming
│   │   │   ├── llm.py              ← LangChain LLM factory + structured output
│   │   │   ├── prompts/            ← versioned prompt templates (.txt/.jinja)
│   │   │   │   ├── explain_issue.jinja
│   │   │   │   ├── nl_to_sql.jinja
│   │   │   │   ├── insights.jinja
│   │   │   │   ├── governance.jinja
│   │   │   │   └── metadata.jinja
│   │   │   └── vector_store.py     ← ChromaDB wrapper (stretch)
│   │   │
│   │   ├── db/
│   │   │   ├── session.py          ← SQLAlchemy engine/session
│   │   │   ├── base.py             ← declarative base
│   │   │   ├── models.py           ← ORM models (see §3)
│   │   │   └── init_db.py          ← create tables + seed demo data
│   │   │
│   │   ├── schemas/                ← Pydantic request/response DTOs
│   │   │   ├── dataset.py
│   │   │   ├── quality.py
│   │   │   ├── chat.py
│   │   │   ├── governance.py
│   │   │   ├── report.py
│   │   │   └── common.py
│   │   │
│   │   ├── core/
│   │   │   ├── security.py         ← password hash, JWT
│   │   │   ├── exceptions.py       ← domain exceptions + handlers
│   │   │   └── storage.py          ← file/parquet storage abstraction
│   │   │
│   │   └── utils/
│   │       ├── type_detect.py
│   │       ├── validators.py       ← email/phone/url/date regex + validators
│   │       └── formatting.py
│   │
│   ├── data/                       ← runtime (gitignored): uploads, parquet, sqlite, chroma
│   │   ├── uploads/  parquet/  reports/  datapilot.db  chroma/
│   ├── samples/                    ← curated demo datasets (messy on purpose!)
│   └── tests/
│       ├── test_engines/  test_agents/  test_api/
│
└── frontend/
    ├── package.json  vite.config.ts  tailwind.config.ts  tsconfig.json
    ├── components.json             ← shadcn config
    ├── index.html
    └── src/
        ├── main.tsx  App.tsx  router.tsx
        ├── lib/
        │   ├── api.ts              ← axios instance + interceptors
        │   ├── queryClient.ts      ← TanStack Query config
        │   ├── sse.ts              ← EventSource helper for streaming
        │   └── utils.ts            ← cn(), formatters
        ├── types/                  ← TS types mirroring backend schemas
        │   ├── dataset.ts  quality.ts  chat.ts  governance.ts  api.ts
        ├── hooks/
        │   ├── useDatasets.ts  useAnalysis.ts  useChat.ts
        │   ├── useUpload.ts  useReports.ts  useAuth.ts
        ├── api/                    ← typed API call functions (one per domain)
        │   ├── datasets.ts  quality.ts  chat.ts  reports.ts  ...
        ├── components/
        │   ├── ui/                 ← shadcn primitives (button, card, dialog…)
        │   ├── layout/             ← AppShell, Sidebar, Topbar, CommandPalette
        │   ├── charts/             ← BarChart, PieChart, LineChart, KpiCard (Recharts)
        │   ├── upload/             ← Dropzone, FormatBadge, UploadProgress
        │   ├── profile/            ← ColumnCard, TypeBadge, StatTile
        │   ├── quality/            ← ScoreGauge, IssueCard, SeverityBadge, DimensionBars
        │   ├── cleaning/           ← CleaningPanel, BeforeAfterDiff
        │   ├── chat/               ← ChatWindow, MessageBubble, SqlBlock, ResultTable
        │   ├── dashboard/          ← AutoDashboard, ChartGrid
        │   ├── governance/         ← SensitivityBadge, MetadataTable, IngestionTier
        │   └── reports/            ← ReportCard, ExportMenu
        ├── pages/
        │   ├── Login.tsx  Dashboard.tsx  Upload.tsx
        │   ├── DatasetOverview.tsx  Quality.tsx  Cleaning.tsx
        │   ├── Chat.tsx  Insights.tsx  Governance.tsx
        │   ├── Reports.tsx  History.tsx  Compare.tsx
        └── styles/  index.css       ← Tailwind + CSS vars (theme tokens)
```

---

## 3. Database Schema (SQLite via SQLAlchemy)

Metadata & history live in SQLite. **Actual data lives in Parquet on disk** (referenced by path). This keeps the DB small and queries fast.

```sql
-- Users (simple local auth)
users(
  id TEXT PK, email TEXT UNIQUE, name TEXT,
  password_hash TEXT, role TEXT DEFAULT 'analyst',
  created_at DATETIME
)

-- Datasets (one row per uploaded file/version)
datasets(
  id TEXT PK, user_id FK->users,
  name TEXT, original_filename TEXT,
  format TEXT,            -- csv|xlsx|json
  encoding TEXT, delimiter TEXT,
  row_count INT, col_count INT,
  file_size_bytes INT, memory_bytes INT,
  parquet_path TEXT, source_path TEXT,
  parent_id FK->datasets NULL,   -- set when this is a CLEANED version
  is_cleaned BOOL DEFAULT 0,
  status TEXT,            -- uploaded|profiled|analyzed|cleaned|error
  created_at DATETIME
)

-- Column profile (one row per column)
columns(
  id TEXT PK, dataset_id FK->datasets,
  name TEXT, ordinal INT,
  physical_type TEXT,     -- int64, float64, object...
  semantic_type TEXT,     -- email|phone|currency|date|zip|lat|lng|url|id|bool|text|numeric
  null_count INT, null_pct REAL, distinct_count INT, cardinality_ratio REAL,
  min_val TEXT, max_val TEXT, mean_val REAL, std_val REAL,
  sample_values JSON,     -- few examples
  -- governance/metadata (filled by governance agent)
  business_name TEXT, description TEXT, sensitivity TEXT, is_pii BOOL,
  owner TEXT
)

-- Analysis runs (a full pipeline execution)
analysis_runs(
  id TEXT PK, dataset_id FK->datasets, user_id FK->users,
  overall_score REAL,
  completeness REAL, accuracy REAL, consistency REAL,
  uniqueness REAL, validity REAL, integrity REAL,
  duplicate_rows INT, total_issues INT,
  duration_ms INT, created_at DATETIME
)

-- Individual quality issues found in a run
issues(
  id TEXT PK, run_id FK->analysis_runs, column_name TEXT NULL,
  check_key TEXT,         -- missing_values|duplicates|invalid_email|outliers...
  severity TEXT,          -- critical|high|medium|low|info
  count INT, sample JSON,
  -- AI explanation (filled by InsightAgent)
  problem TEXT, why TEXT, business_impact TEXT, recommended_fix TEXT,
  confidence REAL,
  created_at DATETIME
)

-- Governance classification (dataset-level)
governance(
  id TEXT PK, dataset_id FK->datasets,
  classification TEXT,    -- public|internal|confidential|sensitive|pii|financial|healthcare
  pii_columns JSON, rationale TEXT,
  ingestion_tier TEXT,    -- bronze|silver|gold
  tier_rationale TEXT,
  created_at DATETIME
)

-- Chat sessions + messages (per dataset)
chat_sessions(id TEXT PK, dataset_id FK, user_id FK, title TEXT, created_at DATETIME)
chat_messages(
  id TEXT PK, session_id FK->chat_sessions,
  role TEXT,              -- user|assistant
  content TEXT,
  generated_sql TEXT NULL,
  result_preview JSON NULL,   -- small table snapshot for re-render
  chart_spec JSON NULL,
  created_at DATETIME
)

-- Generated reports
reports(
  id TEXT PK, dataset_id FK, run_id FK NULL, user_id FK,
  type TEXT,              -- pdf|xlsx|json|csv
  title TEXT, file_path TEXT, size_bytes INT, created_at DATETIME
)

-- Cleaning operations applied (audit trail / before-after)
cleaning_ops(
  id TEXT PK, dataset_id FK, cleaned_dataset_id FK->datasets,
  operations JSON,        -- list of {op, column, params, rows_affected}
  before_score REAL, after_score REAL, created_at DATETIME
)
```

**Relationships:** `users 1─* datasets 1─* columns`; `datasets 1─* analysis_runs 1─* issues`; `datasets 1─1 governance`; `datasets 1─* chat_sessions 1─* chat_messages`; cleaned datasets link back via `parent_id`.

---

## 4. API List (REST v1, prefix `/api/v1`)

| Method | Path | Purpose | Agent(s) | Prio |
|--------|------|---------|----------|------|
| POST | `/auth/login` | Login → JWT | — | 🔴 |
| POST | `/auth/register` | Create user | — | 🔴 |
| GET | `/auth/me` | Current user | — | 🔴 |
| POST | `/datasets` | Upload file (multipart) → summary | Upload | 🔴 |
| GET | `/datasets` | List user's datasets | — | 🔴 |
| GET | `/datasets/{id}` | Dataset summary + status | — | 🔴 |
| DELETE | `/datasets/{id}` | Delete dataset | — | 🟢 |
| GET | `/datasets/{id}/preview` | First N rows | — | 🔴 |
| POST | `/datasets/{id}/analyze` | Run full pipeline (**SSE** progress) | Profiling→Quality→Governance→Insight | 🔴 |
| GET | `/datasets/{id}/profile` | Column profiles + semantic types | Profiling | 🔴 |
| GET | `/datasets/{id}/quality` | Score + issues + severity | Quality | 🔴 |
| GET | `/datasets/{id}/quality/{issue_id}/explain` | AI explanation (stream) | Insight | 🟡 |
| POST | `/datasets/{id}/clean` | Apply cleaning ops → new dataset | Cleaning | 🔴 |
| GET | `/datasets/{id}/clean/preview` | Proposed ops + est. impact | Cleaning | 🟡 |
| GET | `/datasets/{id}/compare/{other_id}` | Before/after or two-dataset diff | — | 🟡 |
| POST | `/datasets/{id}/chat` | NL question → SQL → result (**SSE**) | Chat→SQL | 🔴 |
| GET | `/datasets/{id}/chat/sessions` | List chat sessions | — | 🟡 |
| GET | `/datasets/{id}/dashboard` | Auto-generated chart specs + KPIs | Dashboard | 🔴 |
| GET | `/datasets/{id}/insights` | Business insights (stream) | Insight | 🟡 |
| GET | `/datasets/{id}/recommendations` | Normalization/index/quality recs | Insight | 🟢 |
| GET | `/datasets/{id}/governance` | Classification + PII + tier | Governance | 🟡 |
| GET | `/datasets/{id}/metadata` | Business metadata per column | Governance | 🟡 |
| POST | `/datasets/{id}/reports` | Generate report (type in body) | Report | 🟡 |
| GET | `/reports` / `/reports/{id}/download` | List / download | Report | 🟡 |
| GET | `/history` | Analysis + chat + report history | — | 🟡 |

**Conventions:** JSON everywhere; errors as `{error:{code,message,detail}}`; JWT bearer auth; SSE endpoints emit `event: progress|token|done` frames. All list endpoints paginate (`?limit&offset`).

---

## 5. AI Agent Design (custom orchestrator)

### 5.1 Contract

```python
class AgentContext:        # shared, passed through the pipeline
    dataset_id: str
    df: pd.DataFrame       # loaded once, reused
    profile: Profile | None
    quality: QualityResult | None
    meta: dict             # scratch space + prior agent outputs
    emit(event, payload)   # push SSE progress to client

class Agent(ABC):
    name: str
    def run(self, ctx: AgentContext) -> AgentResult: ...
```

### 5.2 Agents & responsibilities

| Agent | Input | Output | Engine vs LLM | Prio |
|-------|-------|--------|---------------|------|
| **Upload** | raw file | DataFrame, format/encoding/delimiter, summary | Engine (loader) | 🔴 |
| **Profiling** | df | column types, semantic types, stats | Engine (profiler) | 🔴 |
| **Quality** | df + profile | 20+ checks, 6-dim score, severities | Engine (checks+scorer) | 🔴 |
| **Cleaning** | df + quality | cleaning plan + cleaned df + diff | Engine (cleaner) | 🔴 |
| **Governance** | profile + samples | classification, PII cols, ingestion tier, metadata | Rules **+ LLM** | 🟡 |
| **SQL** | NL question + schema | validated SQL string | **LLM** (nl_to_sql) | 🔴 |
| **Dashboard** | profile | chart specs + KPI definitions | Engine (chart_recommender) | 🔴 |
| **Insight** | quality + df stats | issue explanations, trends, actions | **LLM** (streamed) | 🟡 |
| **Report** | run + insights | PDF/Excel/JSON/CSV artifact | Engine (ReportLab/OpenPyXL) | 🟡 |
| **Chat** | NL question | routes to SQL agent, executes via DuckDB, picks chart, narrates | Orchestration + **LLM** | 🔴 |

### 5.3 Orchestrator (the "wow" pipeline)

```
Coordinator.run_analysis(dataset_id):
    ctx = build_context(dataset_id)          # loads df from parquet once
    for agent in [Profiling, Quality, Governance, Insight]:
        ctx.emit("progress", {agent, status:"running"})
        result = agent.run(ctx)              # each agent enriches ctx
        persist(result)
        ctx.emit("progress", {agent, status:"done", summary})
    ctx.emit("done", final_report)
```

- **Sequential with live SSE progress** → the UI shows agents "thinking" one-by-one (Fabric-Copilot vibe). Huge demo value, trivial to build.
- **Safety:** each agent wrapped in try/except → failure emits a degraded result, never crashes the pipeline.
- **LLM guardrails:** SQL agent output is parsed + validated (SELECT-only, table whitelist, `LIMIT` injected) before hitting DuckDB. Structured LLM outputs validated with Pydantic; one retry on parse failure, then deterministic fallback.
- **CrewAI/LangGraph swap point:** `Coordinator` is an interface; a `CrewOrchestrator` can replace `SimpleCoordinator` later without touching services (🟢 stretch).

### 5.4 Chat-with-data flow (critical differentiator)

```
User: "top 10 states by revenue"
 → ChatAgent builds schema context (columns + semantic types)
 → SQLAgent (Groq): NL + schema → SQL      [nl_to_sql.jinja]
 → validate SQL (SELECT-only, add LIMIT)
 → DuckDBEngine.execute(sql over parquet)
 → ChartRecommender picks bar chart (categorical x, numeric y)
 → LLM one-liner narration (streamed)
 → return {answer, sql, table, chart_spec}
```

---

## 6. User Flow

```
Login ──▶ Dashboard (recent datasets, KPIs, quick actions)
              │
              ▼
        Upload (drag-drop CSV/XLSX/JSON) ──▶ instant Summary card
              │
              ▼  [Analyze] → live agent pipeline (SSE progress bar)
              │
   ┌──────────┼───────────────────────────────────────────────┐
   ▼          ▼           ▼            ▼           ▼            ▼
 Profile   Quality     Cleaning     Chat      Dashboard    Governance
 (types,  (score gauge, (1-click,  (ask NL,  (auto charts (PII, tier,
 stats)   issues, AI    before/    SQL+chart) + KPIs)     metadata)
          explain)      after diff)
                            │
                            ▼
                     Insights ──▶ Reports (PDF/Excel/JSON) ──▶ History
```

**Golden demo path (memorize this):** Login → Upload messy sample → watch agents analyze live → see 62/100 score + AI-explained issues → one-click Clean → score jumps to 94/100 with before/after → open Chat, ask a question, get SQL + chart → Governance flags PII + recommends Silver tier → Export PDF. **That's the winning 5 minutes.**

---

## 7. Component Diagram (frontend)

```
<App>
 └─ <QueryClientProvider> <ThemeProvider(dark)> <Router>
     ├─ /login → <Login>
     └─ <AppShell>                       (persistent)
         ├─ <Sidebar> (nav + dataset switcher)
         ├─ <Topbar> (search, user, ⌘K CommandPalette)
         └─ <Outlet>
             ├─ <Dashboard>      → <KpiCard>×4, <RecentDatasets>, <MiniChart>
             ├─ <Upload>         → <Dropzone> → <UploadProgress> → <SummaryCard>
             ├─ <DatasetOverview>→ <SummaryCard>, <PreviewTable>, <AnalyzeButton+SSE>
             ├─ <Quality>        → <ScoreGauge>, <DimensionBars>, <IssueCard(AI)>×N
             ├─ <Cleaning>       → <CleaningPanel>, <BeforeAfterDiff>
             ├─ <Chat>           → <ChatWindow>[<MessageBubble>,<SqlBlock>,<ResultTable>,<ChartRender>]
             ├─ <Insights>       → <InsightCard>×N (streamed)
             ├─ <Dashboard(auto)>→ <ChartGrid>[<Bar/Pie/Line/Scatter>]
             ├─ <Governance>     → <SensitivityBadge>, <MetadataTable>, <IngestionTier>
             ├─ <Reports>        → <ReportCard>, <ExportMenu>
             ├─ <History>        → <HistoryTimeline>
             └─ <Compare>        → <DiffTable>
Shared: <ui/*> shadcn primitives, <charts/*> Recharts wrappers, hooks/* (TanStack Query)
```

**State strategy:** TanStack Query owns *all* server state (caching, invalidation, loading/error). Local UI state via `useState`/`useReducer`. No Redux. SSE handled by a `useAnalysisStream`/`useChatStream` hook feeding component state.

---

## 8. Backend Architecture

- **Layered / clean architecture:** `api` (HTTP) → `services` (use-cases) → `agents`+`engines` (domain) → `db`/`ai`/`storage` (infra). Dependencies point inward. Routers never touch the DB directly.
- **Dependency Injection** via FastAPI `Depends` (`get_db`, `get_current_user`, service providers) → testable, swappable.
- **Config** through `pydantic-settings` reading `.env` (`GROQ_API_KEY`, `GROQ_MODEL`, `DB_URL`, `DATA_DIR`, `JWT_SECRET`).
- **Error handling:** custom exceptions (`DatasetNotFound`, `UnsupportedFormat`, `LLMError`) → global handlers → clean JSON. LLM/DuckDB failures degrade gracefully.
- **Logging:** structured (JSON in prod, pretty in dev), request-id middleware, per-agent timing.
- **Async:** endpoints `async`; heavy pandas work offloaded via `run_in_threadpool` so the event loop stays responsive; SSE via `StreamingResponse`.
- **SOLID:** each engine check is a single-responsibility pure function registered in a `CHECKS` registry (open/closed — add a check without touching the runner). Agents depend on the `Agent` abstraction, not concretions.

---

## 9. Frontend Architecture

- **Vite + React + TS**, path alias `@/`. **Tailwind + shadcn/ui** with dark-first theme tokens (CSS variables) → the "Azure/Fabric" look: deep slate bg, subtle borders, accent gradient, glassy cards.
- **Routing:** React Router with an `<AppShell>` layout route + protected routes (redirect to `/login` if no token).
- **Data:** TanStack Query for every fetch; typed API layer (`src/api/*`) + typed hooks (`src/hooks/*`); axios instance with auth interceptor + error toast.
- **Types:** `src/types/*` mirror backend Pydantic schemas 1:1 (single source of truth via shared shapes).
- **Charts:** thin Recharts wrappers in `components/charts` that consume backend `chart_spec` objects → backend decides *what* to chart, frontend decides *how* to render.
- **UX polish (cheap wins):** skeleton loaders, framer-motion page/stagger transitions, streaming text for AI, toast notifications, `⌘K` command palette, animated score gauge, confetti on "cleaned!". These read as "commercial product".
- **Design system:** consult the `dataviz` skill before building charts; consistent spacing scale, one accent color, semantic severity colors (critical=red, high=orange, medium=amber, low=blue, info=slate).

---

## 10. Development Roadmap (48h, MVP-first)

The roadmap is **vertical-slice first**: get the golden demo path working end-to-end early, then thicken each slice. Never spend hour 40 on something not in the demo.

```
Phase 0 — Foundation (0–4h)  🔴
  Repo scaffold, docker-compose, FastAPI skeleton, Vite+Tailwind+shadcn,
  AppShell + dark theme, health check, one sample messy dataset ready.

Phase 1 — Data Spine (4–12h)  🔴
  Upload+loader (CSV/XLSX/JSON, encoding/delimiter detect) → Parquet + SQLite.
  Profiling engine (types + semantic types + stats). Dataset summary + preview UI.
  Auth (login/register/JWT). Dashboard page shell.

Phase 2 — Quality + AI Narrative (12–24h)  🔴🟡
  Quality engine (20 checks → 6-dim score → severity). SSE analyze pipeline +
  live agent progress UI. ScoreGauge + IssueCards. Groq wired; InsightAgent
  explains issues (streamed). Cleaning engine + one-click clean + before/after.

Phase 3 — Chat + Dashboard (24–36h)  🔴🟡
  DuckDB engine. NL→SQL agent + validation. Chat UI (SQL block + result table +
  auto chart). Auto-dashboard (chart recommender → ChartGrid + KPIs).

Phase 4 — Governance + Reports + Polish (36–44h)  🟡
  Governance agent (PII/classification/tier + metadata table). PDF/Excel export.
  History page. Compare view. Animations, empty states, error toasts, loading skeletons.

Phase 5 — Demo Hardening (44–48h)  🔴
  Seed script, rehearse golden path 3×, fix demo-breaking bugs ONLY, record
  a backup screen-capture, prep pitch. Freeze features at hour 46.
```

**Cut-if-behind order (drop from the bottom):** Compare → Recommendations → Vector/ChromaDB → History → Excel export (keep PDF) → Governance metadata (keep classification badge). **Never cut:** upload, profiling, quality score, AI explanation, cleaning before/after, chat-with-data.

---

## 11. Sprint Planning (2–3 people, two ~24h sprints)

Two tracks running in parallel from hour 0, meeting at a stable API contract (defined in §3–§4, frozen early).

### Sprint 1 (0–24h) — "It works end to end"
**Goal:** golden path demo-able in staging by hour 24 (upload → analyze → score → clean → before/after).

| Track | Owner | Deliverables |
|-------|-------|--------------|
| **Backend/AI** | Dev A (+ Dev C) | Scaffold, loader, profiler, quality checks+scorer, cleaner, SQLite/Parquet, analyze SSE pipeline, Groq InsightAgent, auth. Publish OpenAPI early. |
| **Frontend** | Dev B (+ Dev C) | Scaffold, AppShell+dark theme, auth pages, Upload+Summary, DatasetOverview+preview, Quality (gauge+issues), Cleaning (before/after), SSE progress hook. |

**Sprint 1 review (hour 24):** run golden path top-to-bottom. Triage: what's fragile? Freeze API.

### Sprint 2 (24–48h) — "It wows and it ships"
**Goal:** chat, auto-dashboard, governance, reports, and *polish* that makes it look commercial.

| Track | Owner | Deliverables |
|-------|-------|--------------|
| **Backend/AI** | Dev A | DuckDB engine, NL→SQL agent+guardrails, chart recommender, governance agent, ReportLab/OpenPyXL exports. |
| **Frontend** | Dev B | Chat UI (SQL+table+chart), Auto-dashboard grid+KPIs, Governance page, Reports/Export, History, animations & polish. |
| **Floater** | Dev C | Sample data curation, seed script, demo rehearsal, backup recording, README, bugfix swarm, pitch deck. |

**Ceremonies (lightweight):** 15-min standup at hours 0, 12, 24, 36; hard feature-freeze at hour 46; demo dry-runs at 40, 44, 47.

---

## 12. Task Breakdown (backlog, tagged by priority)

### Backend / AI
- 🔴 BE-01 Project scaffold, config, logging, CORS, health check
- 🔴 BE-02 `storage.py` + SQLite models + `init_db` + seed
- 🔴 BE-03 `loader.py`: detect format/encoding/delimiter, load CSV/XLSX/JSON → df → Parquet
- 🔴 BE-04 Upload endpoint + DatasetService + summary DTO
- 🔴 BE-05 `profiler.py`: physical + semantic type inference (email/phone/date/currency/zip/lat/lng/url/id), stats
- 🔴 BE-06 `quality_checks.py`: 20+ checks as registered pure functions
- 🔴 BE-07 `scorer.py`: 6-dimension score → 0–100 + severity mapping
- 🔴 BE-08 Agent base + `orchestrator.py` + SSE progress
- 🔴 BE-09 `analyze` endpoint (streams pipeline) + persist run/issues
- 🔴 BE-10 `groq_client.py` + LangChain LLM factory + structured output + retry
- 🟡 BE-11 InsightAgent: explain issues (problem/why/impact/fix/confidence), streamed
- 🔴 BE-12 `cleaner.py`: fill/dedupe/trim/standardize/convert/normalize/dates/outliers (idempotent)
- 🔴 BE-13 Clean endpoint → new dataset version + `cleaning_ops` + before/after scores
- 🔴 BE-14 `duckdb_engine.py`: query Parquet, safe execution
- 🔴 BE-15 SQLAgent: `nl_to_sql.jinja` + SQL validation (SELECT-only, LIMIT, table whitelist)
- 🔴 BE-16 ChatAgent + chat endpoint (SSE) + persist messages
- 🔴 BE-17 `chart_recommender.py` + dashboard endpoint (chart specs + KPIs)
- 🟡 BE-18 GovernanceAgent: classification + PII + ingestion tier + metadata
- 🟡 BE-19 ReportService: PDF (ReportLab), Excel (OpenPyXL), JSON/CSV
- 🟡 BE-20 History + Compare endpoints
- 🔴 BE-21 Auth: register/login/JWT + `get_current_user`
- 🟢 BE-22 ChromaDB vector store for semantic column/issue search
- 🟢 BE-23 Recommendations endpoint (normalization/indexes/missing cols)

### Frontend
- 🔴 FE-01 Vite+TS+Tailwind+shadcn scaffold, theme tokens, `@/` alias
- 🔴 FE-02 API client (axios+interceptors), TanStack Query, SSE helper, types
- 🔴 FE-03 AppShell: Sidebar + Topbar + dark theme + responsive
- 🔴 FE-04 Auth pages + protected routes + useAuth
- 🔴 FE-05 Upload: Dropzone + progress + FormatBadge + SummaryCard
- 🔴 FE-06 DatasetOverview: summary tiles + PreviewTable + Analyze button
- 🔴 FE-07 `useAnalysisStream` + live agent progress UI
- 🔴 FE-08 Quality: animated ScoreGauge + DimensionBars + IssueCard + SeverityBadge
- 🟡 FE-09 IssueCard AI explanation (streamed text)
- 🔴 FE-10 Cleaning: CleaningPanel + BeforeAfterDiff (metric deltas)
- 🔴 FE-11 Chat: ChatWindow, MessageBubble, SqlBlock (syntax hl), ResultTable, ChartRender
- 🔴 FE-12 Auto-dashboard: ChartGrid + KpiCards (Recharts wrappers)
- 🟡 FE-13 Governance: SensitivityBadge + MetadataTable + IngestionTier
- 🟡 FE-14 Reports: ReportCard + ExportMenu + download
- 🟡 FE-15 History timeline
- 🟡 FE-16 Compare / DiffTable
- 🟡 FE-17 Polish: framer-motion, skeletons, toasts, ⌘K palette, empty states
- 🔴 FE-18 Landing Dashboard: KPIs + recent datasets + quick actions

### DevOps / Demo (floater)
- 🔴 OP-01 docker-compose + Makefile (`dev`/`seed`/`demo`) + `.env.example`
- 🔴 OP-02 Curate 2–3 deliberately-messy demo datasets (sales, customers w/ PII, HR)
- 🔴 OP-03 Seed script (pre-loaded demo user + dataset for instant start)
- 🟡 OP-04 README with screenshots + architecture diagram
- 🔴 OP-05 Golden-path rehearsal + backup screen recording
- 🔴 OP-06 Pitch deck (problem → demo → architecture → business value)

---

## Appendix A — The 20+ Quality Checks (engine registry)

| Dimension | Checks |
|-----------|--------|
| **Completeness** | missing values, null %, blank strings |
| **Uniqueness** | duplicate rows, duplicate columns, constant columns, high/low cardinality |
| **Validity** | invalid emails, invalid phones, invalid URLs, invalid dates, negative values (where illogical) |
| **Consistency** | leading/trailing spaces, case inconsistency, mixed datatypes, unicode issues, schema drift |
| **Accuracy** | datatype mismatch, outliers (IQR/z-score) |
| **Integrity** | referential/format integrity, ID uniqueness |

Each check returns `{check_key, column, severity, count, sample}` and contributes a penalty to its dimension. `overall = weighted_avg(dimensions)`.

## Appendix B — Tech-stack lock (versions to pin at scaffold)

Backend: `fastapi`, `uvicorn[standard]`, `pandas`, `numpy`, `duckdb`, `pyarrow`, `sqlalchemy`, `pydantic-settings`, `python-multipart`, `groq`, `langchain`, `langchain-groq`, `reportlab`, `openpyxl`, `chardet`, `python-jose`, `passlib[bcrypt]`, `jinja2`, `chromadb` (stretch).
Frontend: `react`, `react-dom`, `react-router-dom`, `@tanstack/react-query`, `axios`, `recharts`, `react-hook-form`, `zod`, `tailwindcss`, shadcn/ui, `framer-motion`, `lucide-react`, `sonner` (toasts).

**LLM:** Groq `llama-3.3-70b-versatile` (fast, strong at SQL/JSON). Keep model id in config for one-line swap.
