"""Custom validation service: AI proposes a rule, user approves, it's enforced."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.agents.profiling_agent import ProfilingAgent
from app.constants.enums import Dimension, Severity
from app.core.engines.duckdb_engine import DuckDBEngine
from app.core.llm import prompts
from app.core.llm.groq_client import get_llm
from app.exceptions.base import BadRequestException, NotFoundException
from app.repositories.custom_validation_repository import CustomValidationRepository
from app.schemas.ai import CustomValidationItem, ValidationProposal
from app.services.base import BaseService, DatasetContextMixin

_VALID_DIMENSIONS = {d.value for d in Dimension}
_VALID_SEVERITIES = {s.value for s in Severity}


class CustomValidationService(BaseService, DatasetContextMixin):
    """Turns a natural-language request into an approvable, enforceable rule."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.validations = CustomValidationRepository(db)
        self.profiling_agent = ProfilingAgent()
        self.duck = DuckDBEngine()
        self.llm = get_llm()

    # ---- propose (AI) -------------------------------------------------- #
    def propose(self, dataset_id: int, user_id: int, prompt: str) -> ValidationProposal:
        """Interpret the prompt into a rule and preview which rows it flags."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        ctx = self._build_context(dataset)
        self.profiling_agent.run(ctx)
        assert ctx.profile is not None
        schema = ", ".join(f"{c.name}: {c.semantic_type}" for c in ctx.profile.columns)

        plan = self._plan(prompt, schema)
        generated_by = "ai" if plan.get("_ai") else "fallback"

        condition = str(plan.get("condition") or "").strip()
        if not condition:
            raise BadRequestException(
                "Couldn't turn that into a rule. Try naming a column and a condition, "
                "e.g. \"flag rows where SALE_PRICE is 0\"."
            )
        dimension = plan.get("dimension") if plan.get("dimension") in _VALID_DIMENSIONS else "validity"
        severity = plan.get("severity") if plan.get("severity") in _VALID_SEVERITIES else "medium"
        name = str(plan.get("name") or "Custom validation").strip()[:255]
        description = str(plan.get("description") or "").strip()

        df = self._read_frame(dataset)
        # Runs + validates the condition. Text columns that hold numbers/dates need
        # an explicit cast; if the model missed it, self-heal once.
        try:
            count, _idx, cols, rows = self.duck.evaluate_condition(df, condition, sample_limit=10)
        except BadRequestException as exc:
            repaired = self._repair_condition(condition, str(exc), schema)
            if repaired and repaired != condition:
                condition = repaired
                count, _idx, cols, rows = self.duck.evaluate_condition(df, condition, sample_limit=10)
            else:
                raise

        return ValidationProposal(
            name=name, description=description, dimension=dimension, severity=severity,
            condition=condition, matched_rows=count, total_rows=int(len(df)),
            sample_columns=cols, sample_rows=rows, generated_by=generated_by,
        )

    def _repair_condition(self, condition: str, error: str, schema: str) -> str | None:
        """Fix a condition that failed a type/cast check.

        First a deterministic pass wraps bare column comparisons in TRY_CAST;
        if the LLM is available it also gets one repair attempt.
        """
        if "cast" not in error.lower() and "compare" not in error.lower():
            return None

        # Deterministic: wrap "col" <op> <number>  ->  TRY_CAST("col" AS DOUBLE) <op> <number>
        import re

        def wrap(m: re.Match) -> str:
            return f'TRY_CAST({m.group(1)} AS DOUBLE) {m.group(2)} {m.group(3)}'

        fixed = re.sub(
            r'("(?:[^"]|"")+")\s*(>=|<=|<>|!=|=|>|<)\s*(-?\d+(?:\.\d+)?)',
            wrap, condition,
        )
        if fixed != condition:
            return fixed

        # LLM repair as a fallback.
        if self.llm.available:
            raw = self.llm.complete_json(
                "You fix a DuckDB WHERE condition that failed. Wrap text columns compared to "
                'numbers/dates in TRY_CAST("col" AS DOUBLE) or TRY_CAST("col" AS DATE). '
                'Return STRICT JSON {"condition": "..."} only.',
                f"Columns: {schema}\nCondition: {condition}\nError: {error}",
            )
            if isinstance(raw, dict) and raw.get("condition"):
                return str(raw["condition"])
        return None

    def _plan(self, prompt: str, schema: str) -> dict:
        if self.llm.available:
            raw = self.llm.complete_json(
                prompts.CUSTOM_VALIDATION_SYSTEM,
                prompts.CUSTOM_VALIDATION_USER.format(schema=schema, prompt=prompt),
            )
            if isinstance(raw, dict) and raw.get("condition"):
                raw["_ai"] = True
                return raw
        return self._heuristic(prompt, schema)

    @staticmethod
    def _heuristic(prompt: str, schema: str) -> dict:
        """Deterministic fallback: parse '<column> <op> <value>' style requests."""
        cols = [c.split(":")[0].strip() for c in schema.split(",") if ":" in c]
        q = prompt.strip()
        low = q.lower()
        # Find a column mentioned in the prompt (longest first).
        col = next((c for c in sorted(cols, key=len, reverse=True)
                    if c.lower() in low or c.lower().replace("_", " ") in low), None)
        if not col:
            return {"condition": "", "name": "Custom validation"}

        def quoted(c: str) -> str:
            return '"' + c.replace('"', '""') + '"'

        cond = None
        if "null" in low or "empty" in low or "missing" in low or "blank" in low:
            cond = f"{quoted(col)} IS NULL"
        else:
            m = re.search(r"(=|==|!=|>=|<=|>|<|equals?|greater than|less than)\s*([\-\w.]+)", low)
            num = re.search(r"(-?\d+(?:\.\d+)?)", low.split(col.lower())[-1] if col.lower() in low else low)
            op_map = {"equals": "=", "equal": "=", "==": "=", "greater than": ">", "less than": "<"}
            if m:
                op = op_map.get(m.group(1), m.group(1))
                val = m.group(2)
                if re.match(r"^-?\d+(\.\d+)?$", val):
                    # Numeric comparison — cast so text-stored numbers still work.
                    cond = f"TRY_CAST({quoted(col)} AS DOUBLE) {op} {val}"
                else:
                    cond = f"{quoted(col)} {op} '{val}'"
            elif num:
                cond = f"TRY_CAST({quoted(col)} AS DOUBLE) = {num.group(1)}"
        if not cond:
            return {"condition": "", "name": "Custom validation"}
        return {
            "condition": cond,
            "name": f"Check on {col}",
            "description": f"Flags rows where {col} matches the condition {cond}.",
            "dimension": "validity",
            "severity": "medium",
        }

    # ---- create / list / delete ---------------------------------------- #
    def create(self, dataset_id: int, user_id: int, data) -> CustomValidationItem:
        """Persist an approved validation (after re-checking its condition)."""
        dataset = self._load_owned_dataset(dataset_id, user_id)
        df = self._read_frame(dataset)
        self.duck.evaluate_condition(df, data.condition, sample_limit=1)  # validate SQL

        dimension = data.dimension if data.dimension in _VALID_DIMENSIONS else "validity"
        severity = data.severity if data.severity in _VALID_SEVERITIES else "medium"
        row = self.validations.create(
            dataset_id=dataset_id, user_id=user_id, name=data.name[:255],
            description=data.description, dimension=dimension, severity=severity,
            condition=data.condition, is_active=True, created_by=user_id,
        )
        self.db.commit()
        return CustomValidationItem.model_validate(row)

    def list(self, dataset_id: int, user_id: int) -> list[CustomValidationItem]:
        self._load_owned_dataset(dataset_id, user_id)
        return [CustomValidationItem.model_validate(v) for v in self.validations.list_for_dataset(dataset_id)]

    def delete(self, dataset_id: int, validation_id: int, user_id: int) -> None:
        self._load_owned_dataset(dataset_id, user_id)
        row = self.validations.get(validation_id)
        if row is None or row.dataset_id != dataset_id:
            raise NotFoundException("Validation not found.")
        self.validations.soft_delete(row)
        self.db.commit()
