"""Enumerations used across engines, agents and schemas."""

from __future__ import annotations

from enum import StrEnum


class SemanticType(StrEnum):
    """Inferred business meaning of a column."""

    NUMERIC = "numeric"
    INTEGER = "integer"
    TEXT = "text"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    CURRENCY = "currency"
    PHONE = "phone"
    EMAIL = "email"
    LATITUDE = "latitude"
    LONGITUDE = "longitude"
    ZIP = "zip"
    ID = "id"
    URL = "url"
    CATEGORICAL = "categorical"


class Severity(StrEnum):
    """Issue severity levels (ordered from most to least severe)."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Dimension(StrEnum):
    """Six quality dimensions that compose the overall score."""

    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"
    CONSISTENCY = "consistency"
    UNIQUENESS = "uniqueness"
    VALIDITY = "validity"
    INTEGRITY = "integrity"


class Classification(StrEnum):
    """Data governance sensitivity classifications."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SENSITIVE = "sensitive"
    PII = "pii"
    FINANCIAL = "financial"
    HEALTHCARE = "healthcare"


class IngestionTier(StrEnum):
    """Medallion architecture ingestion tiers."""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class CompareVerdict(StrEnum):
    """Overall outcome when comparing two versions of a dataset."""

    IMPROVED = "improved"        # quality rose materially
    REGRESSED = "regressed"      # quality fell materially
    MIXED = "mixed"              # gains in one area, losses in another
    EQUIVALENT = "equivalent"    # no material change
    UNKNOWN = "unknown"          # one side has not been quality-scored


class LlmStatus(StrEnum):
    """Live health of the LLM layer, surfaced on the dashboard."""

    ACTIVE = "active"              # configured and the last call succeeded
    DEGRADED = "degraded"          # configured, but the last call failed
    UNCONFIGURED = "unconfigured"  # enabled with no usable API key
    DISABLED = "disabled"          # switched off via settings


class ApprovalStatus(StrEnum):
    """Human approval gate states for a dataset."""

    NOT_REQUIRED = "not_required"  # quality is good enough; auto-cleared
    PENDING = "pending"            # quality below threshold; needs human review
    APPROVED = "approved"          # a human accepted the dataset despite low quality
    REJECTED = "rejected"          # a human rejected the dataset


# Datasets scoring below this need human approval before they're cleared for use.
APPROVAL_THRESHOLD: float = 75.0


# Severity ordering + numeric penalty weight used by the scorer.
# Column-level checks describe the whole column, not individual rows — so their
# "N affected" count means columns/relationships, not rows. They are listed as
# issues but never dirty a row for scoring purposes.
COLUMN_LEVEL_CHECKS: set[str] = {
    "constant_column", "duplicate_columns", "high_cardinality",
    "low_cardinality", "datatype_mismatch",
}

SEVERITY_ORDER: dict[str, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}
