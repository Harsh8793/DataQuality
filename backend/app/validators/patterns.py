"""Regex-based value validators shared by the profiler and quality engine."""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
# International-friendly phone: optional +, 7-15 digits, common separators.
PHONE_RE = re.compile(r"^\+?[\d\s().\-]{7,20}$")
PHONE_DIGITS_RE = re.compile(r"\d")
URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
CURRENCY_RE = re.compile(r"^[\s]*[$€£₹¥]?\s?-?\d{1,3}(,\d{3})*(\.\d+)?\s*[$€£₹¥]?\s*$")
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",   # SQL datetime with milliseconds (e.g. 2021-04-28 16:11:22.010)
    "%Y-%m-%dT%H:%M:%S",       # ISO 8601
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y/%m/%d %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%m-%d-%Y",
    "%d %b %Y",
    "%d %B %Y",
)


def is_valid_email(value: str) -> bool:
    """Return True if the string is a syntactically valid email address."""
    return bool(EMAIL_RE.match(value.strip()))


def is_valid_phone(value: str) -> bool:
    """Return True if the string looks like a valid phone number."""
    value = value.strip()
    if not PHONE_RE.match(value):
        return False
    return 7 <= len(PHONE_DIGITS_RE.findall(value)) <= 15


def is_valid_url(value: str) -> bool:
    """Return True if the string is a valid http(s) URL."""
    return bool(URL_RE.match(value.strip()))


def looks_like_currency(value: str) -> bool:
    """Return True if the string looks like a currency amount."""
    return bool(CURRENCY_RE.match(value.strip())) and any(c.isdigit() for c in value)


def is_valid_zip(value: str) -> bool:
    """Return True if the string is a US-style ZIP code."""
    return bool(ZIP_RE.match(value.strip()))


def is_valid_date(value: str) -> bool:
    """Return True if the string parses as a date/datetime.

    Tries a fast list of common formats first, then falls back to pandas'
    robust parser so unusual-but-valid formats (timezones, other separators)
    aren't mistakenly flagged invalid.
    """
    from datetime import datetime

    text = value.strip()
    if not text:
        return False
    for fmt in _DATE_FORMATS:
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            continue
    # Robust fallback for formats not enumerated above.
    try:
        import pandas as pd

        return not pd.isna(pd.to_datetime(text, errors="coerce"))
    except Exception:  # noqa: BLE001 - never raise from a validator
        return False
