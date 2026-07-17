# DataPilot AI — Architecture

This document covers the agent design as required for submission: the **agent node
diagram**, **state management approach**, **human-in-the-loop (HITL) gate design**,
**tool registry**, and **memory strategy**. For the full system design (DB schema,
API surface, folder layout) see [../ARCHITECTURE.md](../ARCHITECTURE.md).

---

## 1. Overview

DataPilot AI is a **deterministic-core, AI-assisted** agent. The heavy lifting
(profiling, quality checks, scoring, cleaning, SQL execution) runs in deterministic
Python engines; a Groq LLM adds the language/reasoning layer (explanations,
NL→SQL, NL→rule, narration, classification text). Every LLM path has a
deterministic fallback, so the agent degrades gracefully when the model is
rate-limited or offline.

```
Browser (React SPA)
      │  HTTPS  /api/v1/*
      ▼
FastAPI  ──►  Service layer  ──►  Repository layer  ──►  SQLite (metadata)
                   │                                     Parquet files (row data)
                   ├──► Engines  (Pandas · NumPy · DuckDB · ReportLab · OpenPyXL)
                   └──► Agents   (Groq LLM) + SimpleCoordinator
```

---

## 2. Agent node diagram

The analysis pipeline is a sequential graph run by `SimpleCoordinator`
(`backend/app/agents/orchestrator.py`) over a shared `AgentContext`. Interactive
agents (Chat, Custom-Validation, Insight, Explain) run on demand from their
endpoints.

### 2a. Analysis pipeline (runs on upload/analyze/fix/edit)

```
             ┌──────────────────────────── AgentContext (shared state) ───────────────────────────┐
             │  df · profile · findings · score · meta{governance, custom_meta, is_cleaned} · emit │
             └───────────────────────────────────────────────────────────────────────────────────┘
 upload ──► [UploadAgent] ─► [ProfilingAgent] ─► [QualityAgent] ─► [GovernanceAgent] ─► persist ─► HITL gate
 (loader)      parse         semantic types       20+ checks         PII / class /                  approval_status
                             + stats              + Scorer           tier (rules+LLM)               = pending if score<75
                                                       │
                                       custom validations evaluated  ──►  re-score
                                       user exclusions removed        ──►  re-score
```

- **UploadAgent** — detect encoding/delimiter, load CSV/Excel/JSON → DataFrame (deterministic).
- **ProfilingAgent** — 14 semantic types, null %, cardinality, min/max/mean (deterministic).
- **QualityAgent** — runs the check registry (20+ checks) and the Scorer (deterministic).
- **GovernanceAgent** — deterministic PII/classification/tier; LLM only enriches column names/descriptions.
- **Custom validations** — user-defined DuckDB conditions appended as findings, then re-scored.
- **InsightAgent** — business insights; run **on demand** by the Insights tab (kept out of the
  pipeline to save tokens).

### 2b. Interactive agents (per user action)

```
Chat message ─► [ChatAgent] ── plan ──► converse ─► narrated answer
                     │           │
                     │           └────► SQL (DuckDB, read-only) ─► table + auto chart + narration
                     └─ deterministic fallback (pattern-SQL) if LLM unavailable/deflects

"add validation" ─► [CustomValidationService] ─► LLM proposes condition ─► preview (count+sample)
                                                   ─► HUMAN APPROVES ─► persisted as a live check

widget "Explain this" ─► [AiService.explain] ─► LLM (or deterministic summary)
```

---

## 3. State management approach

- **Request/analysis state — `AgentContext`** (`agents/base.py`): a single mutable
  object threaded through the pipeline. Each agent reads prior fields and writes its
  own (`profile`, `findings`, `score`, `meta[...]`). This keeps agents decoupled — they
  communicate only via the context, never by calling each other.
- **Persistent state — SQLite + Parquet.** Metadata (datasets, columns, quality
  reports/issues, governance, chat, edits, fixes, exclusions, custom validations) lives
  in SQLite via SQLAlchemy models and the Repository pattern. The actual row data is
  stored as **Parquet** per dataset; DuckDB queries it read-only for chat and validations.
- **Client state — React Query.** The frontend caches server state by query keys
  (`["dataset", id, "quality"]`, etc.); mutations (fix, edit, exclude, add-validation)
  update/invalidate those keys so the UI reflects re-analysis immediately.
- **Idempotent re-analysis.** `analyze()` is safe to re-run; every fix/edit/validation
  change re-runs it so the score and issue list always reflect current data.

---

## 4. Human-in-the-loop (HITL) gate design

There are three explicit human-approval points; the agent never mutates trusted data
or enforces a new rule without a human decision.

1. **Quality approval gate.** After analysis, datasets scoring below
   `APPROVAL_THRESHOLD` (75) are set to `approval_status = "pending"`. The UI shows a
   *"Needs review"* banner with **Approve / Reject**; the dataset is not treated as
   cleared for downstream use until a human acts. Scores ≥ 75 → `not_required`.
   (`AnalysisService.analyze` + `DatasetService.set_approval`.)
2. **Custom-validation approval.** A natural-language rule is first **proposed** — the
   agent returns the generated condition, matched-row count and a sample — and is only
   persisted/enforced after the user clicks **Approve & add**. (propose → approve → create.)
3. **Reversible fixes / edits.** Every one-click fix, "Fix all", and manual edit is
   snapshotted and **undoable**, and any validation can be **Ignored** (excluded from the
   score, reversibly) — so automated actions are always human-overridable.

---

## 5. Tool registry

The agent's "tools" are the deterministic engines and integrations it invokes.

| Tool | Module | Purpose |
|------|--------|---------|
| Loader | `core/engines/loader.py` | Encoding/delimiter detection, file → DataFrame |
| Profiler | `core/engines/profiler.py` | Semantic typing + column statistics |
| Quality registry | `core/engines/quality_checks.py` | 20+ pluggable checks (`@register`) |
| Scorer | `core/engines/scorer.py` | 6-dimension weighted 0–100 score |
| Cleaner | `core/engines/cleaner.py` | Deterministic multi-step cleaning |
| Fixer | `core/engines/fixer.py` | Targeted per-issue fixes |
| Affected-rows | `core/engines/affected.py` | Row masks per issue |
| DuckDB engine | `core/engines/duckdb_engine.py` | Validated **read-only** SQL + condition eval |
| Chart recommender | `core/engines/chart_recommender.py` | KPI/chart specs + NL widget build |
| Explanations | `core/engines/explanations.py` | Deterministic per-issue explanations |
| Report writer | `services/report_service.py` | PDF/Excel with charts (ReportLab/OpenPyXL) |
| Groq LLM | `core/llm/groq_client.py` | Resilient chat/JSON completions (fallbacks) |
| Prompt registry | `core/llm/prompts.py` | Versioned prompt templates |

The **quality check registry** is the clearest example: adding a validation is one
decorated pure function — `@register def check_x(df, profile) -> list[QualityFinding]`.
User-defined validations extend this at runtime via stored DuckDB conditions.

SQL safety: the DuckDB engine only allows a single read-only `SELECT`/`WITH`, blocks
DDL/DML keywords, and always applies a `LIMIT` — so NL→SQL and NL→rule can never
mutate data.

---

## 6. Memory strategy

- **Conversation memory (chat).** Chat turns are persisted to SQLite (`chat_history`
  sessions + `chat_messages`). On each new message the last ~8 turns (with the SQL each
  ran) are passed to the planner, so follow-ups like *"generate the graph"* or *"now as
  a pie chart"* resolve against prior context. History is restored on reload/login and
  is per dataset; it can be cleared by the user.
- **Cached AI artifacts.** The AI **data story** is generated once and cached on the
  dataset (`story` column) to avoid repeat token spend; it can be regenerated on demand.
- **Learned/derived state.** Column profiles, quality reports, governance, fixes (with
  before/after snapshots), edits (undo history), exclusions and custom validations are
  all persisted, so the agent's understanding of a dataset survives restarts and informs
  every subsequent action.
- **Token discipline.** Deterministic engines handle anything that doesn't need language;
  the LLM is called only for explanation/reasoning, results are cached where possible, and
  every call has a fallback — keeping the agent usable within free-tier limits.
