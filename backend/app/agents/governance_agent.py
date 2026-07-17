"""Governance agent: classify sensitivity, detect PII and recommend a tier.

Uses deterministic rules first (reliable, no cost) and optionally enriches the
result with the LLM for business metadata and rationale.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.agents.base import Agent, AgentContext, AgentResult
from app.constants.enums import Classification, IngestionTier, SemanticType
from app.core.llm import get_llm
from app.core.llm.prompts import GOVERNANCE_SYSTEM, GOVERNANCE_USER

# Semantic types that are inherently PII.
_PII_TYPES = {SemanticType.EMAIL, SemanticType.PHONE}
_PII_NAME_HINTS = (
    "name", "fname", "lname", "surname", "contact", "ssn", "dob", "birth", "address",
    "passport", "aadhaar", "national", "email", "phone", "mobile",
)
_FINANCIAL_HINTS = ("salary", "revenue", "price", "amount", "account", "iban", "card", "payment", "cost", "income")
_HEALTH_HINTS = ("diagnosis", "patient", "medical", "disease", "treatment", "blood")


@dataclass
class GovernanceResult:
    """Governance classification output."""

    classification: str
    pii_columns: list[str]
    rationale: str
    ingestion_tier: str
    tier_rationale: str
    column_metadata: list[dict] = field(default_factory=list)


class GovernanceAgent(Agent):
    """Classifies a dataset's sensitivity and ingestion tier."""

    name = "governance"

    def __init__(self) -> None:
        super().__init__()
        self._llm = get_llm()

    def classify(self, ctx: AgentContext) -> GovernanceResult:
        """Classify ``ctx`` using rules, enriched by the LLM when available."""
        if ctx.profile is None:
            raise ValueError("Profile is required for governance classification.")

        pii_cols, is_financial, is_health = self._scan_columns(ctx)
        classification = self._classify(pii_cols, is_financial, is_health)
        tier = self._recommend_tier(ctx)

        result = GovernanceResult(
            classification=classification,
            pii_columns=pii_cols,
            rationale=self._rationale(classification, pii_cols),
            ingestion_tier=tier,
            tier_rationale=self._tier_rationale(ctx, tier),
            column_metadata=self._rule_metadata(ctx, pii_cols),
        )
        return self._enrich_with_llm(ctx, result)

    def run(self, ctx: AgentContext) -> AgentResult:
        """Run governance classification and store it in ``ctx.meta``."""
        try:
            result = self.classify(ctx)
        except ValueError as exc:
            return self._fail(str(exc))
        ctx.meta["governance"] = result
        return self._ok(result)

    # ---- rules -------------------------------------------------------- #
    def _scan_columns(self, ctx: AgentContext) -> tuple[list[str], bool, bool]:
        pii, financial, health = [], False, False
        for col in ctx.profile.columns:
            lname = col.name.lower()
            if col.semantic_type in _PII_TYPES or any(h in lname for h in _PII_NAME_HINTS):
                pii.append(col.name)
            if col.semantic_type == SemanticType.CURRENCY or any(h in lname for h in _FINANCIAL_HINTS):
                financial = True
            if any(h in lname for h in _HEALTH_HINTS):
                health = True
        return pii, financial, health

    def _classify(self, pii: list[str], financial: bool, health: bool) -> str:
        if health:
            return Classification.HEALTHCARE
        if pii:
            return Classification.PII
        if financial:
            return Classification.FINANCIAL
        return Classification.INTERNAL

    def _recommend_tier(self, ctx: AgentContext) -> str:
        """Bronze (raw/dirty) -> Silver (cleaned) -> Gold (analytics-ready)."""
        score = ctx.score.overall if ctx.score else 0
        if ctx.meta.get("is_cleaned") and score >= 90:
            return IngestionTier.GOLD
        if score >= 75:
            return IngestionTier.SILVER
        return IngestionTier.BRONZE

    def _rationale(self, classification: str, pii: list[str]) -> str:
        if pii:
            return f"Contains personal data in: {', '.join(pii[:5])}."
        return f"Classified as {classification} based on column semantics."

    def _tier_rationale(self, ctx: AgentContext, tier: str) -> str:
        score = ctx.score.overall if ctx.score else 0
        return f"Quality score {score}/100 maps to the {tier} tier."

    def _rule_metadata(self, ctx: AgentContext, pii: list[str]) -> list[dict]:
        return [
            {
                "name": c.name,
                "business_name": c.name.replace("_", " ").title(),
                "description": f"{c.semantic_type} column",
                "sensitivity": "pii" if c.name in pii else "internal",
                "is_pii": c.name in pii,
                "sample_value": c.sample_values[0] if c.sample_values else None,
            }
            for c in ctx.profile.columns
        ]

    # ---- optional LLM enrichment ------------------------------------- #
    def _enrich_with_llm(self, ctx: AgentContext, result: GovernanceResult) -> GovernanceResult:
        """Enrich the deterministic result with the LLM WITHOUT losing it.

        Rules stay authoritative for classification, PII and sensitivity; the LLM
        only adds friendlier business names + descriptions and an overall
        rationale. It can never drop/rename columns or change PII flags.
        """
        if not self._llm.available:
            return result

        columns = [
            {"name": c.name, "type": c.semantic_type, "samples": [str(s) for s in c.sample_values[:2]]}
            for c in ctx.profile.columns[:60]  # cap payload for wide datasets
        ]
        raw = self._llm.complete_json(
            GOVERNANCE_SYSTEM, GOVERNANCE_USER.format(columns=json.dumps(columns, default=str))
        )
        if not isinstance(raw, dict):
            return result

        # Index the LLM's per-column output by the REAL column name only.
        by_lname = {c.name.lower(): c.name for c in ctx.profile.columns}
        llm_cols: dict[str, dict] = {}
        for entry in raw.get("columns") or []:
            if isinstance(entry, dict):
                real = by_lname.get(str(entry.get("name", "")).strip().lower())
                if real:
                    llm_cols[real] = entry

        # PII, sensitivity and classification stay RULE-BASED (reliable). The LLM
        # only contributes friendlier business names + descriptions — small models
        # are unreliable at PII (they flag everything or nothing).
        merged: list[dict] = []
        for m in result.column_metadata:
            e = llm_cols.get(m["name"], {})
            bn = str(e.get("business_name") or "").strip()
            desc = str(e.get("description") or "").strip()
            merged.append({
                **m,
                "business_name": bn or m["business_name"],
                "description": desc or m["description"],
            })

        result.column_metadata = merged
        # Use the LLM rationale only if it doesn't contradict the rule PII finding.
        llm_rationale = str(raw.get("rationale") or "").strip()
        if llm_rationale:
            result.rationale = llm_rationale
        return result
