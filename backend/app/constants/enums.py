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


class ApprovalStatus(StrEnum):
    """Human approval gate states for a dataset."""

    NOT_REQUIRED = "not_required"  # quality is good enough; auto-cleared
    PENDING = "pending"            # quality below threshold; needs human review
    APPROVED = "approved"          # a human accepted the dataset despite low quality
    REJECTED = "rejected"          # a human rejected the dataset


# Datasets scoring below this need human approval before they're cleared for use.
APPROVAL_THRESHOLD: float = 75.0


# Severity ordering + numeric penalty weight used by the scorer.
SEVERITY_WEIGHT: dict[str, float] = {
    Severity.CRITICAL: 45.0,
    Severity.HIGH: 25.0,
    Severity.MEDIUM: 14.0,
    Severity.LOW: 5.0,
    Severity.INFO: 1.0,
}

SEVERITY_ORDER: dict[str, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}
