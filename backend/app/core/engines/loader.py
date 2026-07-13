"""File loading engine: detect format/encoding/delimiter and load to a DataFrame."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

import chardet
import pandas as pd

from app.core.logging import get_logger
from app.exceptions.base import BadRequestException, UnsupportedFormatException

logger = get_logger(__name__)

_SUPPORTED = {"csv", "xlsx", "xls", "json"}


@dataclass
class LoadResult:
    """Outcome of loading a raw file into a DataFrame."""

    df: pd.DataFrame
    file_format: str
    encoding: str | None = None
    delimiter: str | None = None
    warnings: list[str] = field(default_factory=list)


class DataLoader:
    """Loads CSV/Excel/JSON bytes into a normalized pandas DataFrame."""

    def load(self, content: bytes, extension: str) -> LoadResult:
        """Load raw bytes according to the file extension."""
        ext = extension.lower().lstrip(".")
        if ext not in _SUPPORTED:
            raise UnsupportedFormatException(f"Unsupported file format: '{ext}'.")

        if ext == "csv":
            return self._load_csv(content)
        if ext in {"xlsx", "xls"}:
            return self._load_excel(content, ext)
        return self._load_json(content)

    # ---- CSV ---------------------------------------------------------- #
    def _detect_encoding(self, content: bytes) -> str:
        """Detect text encoding, defaulting to utf-8 on low confidence."""
        guess = chardet.detect(content[:100_000])
        encoding = guess.get("encoding") or "utf-8"
        if (guess.get("confidence") or 0) < 0.5:
            encoding = "utf-8"
        return encoding

    # Candidate delimiters, including uncommon ones like tilde and pipe.
    _DELIMITERS = [",", ";", "\t", "|", "~", ":", "^"]

    def _detect_delimiter(self, sample: str) -> str:
        """Detect the CSV delimiter robustly, defaulting to comma.

        Scores each candidate by how many times it appears on the header line
        (so uncommon delimiters like ``~`` or ``|`` are detected), then falls
        back to :class:`csv.Sniffer` and finally a comma.
        """
        header = next((line for line in sample.splitlines() if line.strip()), "")
        counts = {d: header.count(d) for d in self._DELIMITERS}
        best = max(counts, key=counts.get)
        if counts[best] > 0:
            return best
        try:
            return csv.Sniffer().sniff(sample, delimiters="".join(self._DELIMITERS)).delimiter
        except csv.Error:
            return ","

    def _load_csv(self, content: bytes) -> LoadResult:
        encoding = self._detect_encoding(content)
        try:
            text = content.decode(encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            encoding = "utf-8"
            text = content.decode(encoding, errors="replace")

        delimiter = self._detect_delimiter(text[:8192])
        df = pd.read_csv(io.StringIO(text), sep=delimiter, skipinitialspace=False)
        logger.info("Loaded CSV: %d rows x %d cols (enc=%s, delim=%r)", len(df), df.shape[1], encoding, delimiter)
        return LoadResult(df=df, file_format="csv", encoding=encoding, delimiter=delimiter)

    # ---- Excel -------------------------------------------------------- #
    def _load_excel(self, content: bytes, ext: str) -> LoadResult:
        try:
            df = pd.read_excel(io.BytesIO(content))
        except Exception as exc:  # pragma: no cover - defensive
            raise BadRequestException(f"Could not read Excel file: {exc}") from exc
        logger.info("Loaded Excel: %d rows x %d cols", len(df), df.shape[1])
        return LoadResult(df=df, file_format=ext)

    # ---- JSON --------------------------------------------------------- #
    def _load_json(self, content: bytes) -> LoadResult:
        encoding = self._detect_encoding(content)
        text = content.decode(encoding, errors="replace")
        try:
            df = pd.read_json(io.StringIO(text))
        except ValueError:
            # Fall back to records / normalized nested JSON.
            import json

            data = json.loads(text)
            if isinstance(data, dict):
                data = data.get("data", data)
            df = pd.json_normalize(data)
        logger.info("Loaded JSON: %d rows x %d cols", len(df), df.shape[1])
        return LoadResult(df=df, file_format="json", encoding=encoding)
