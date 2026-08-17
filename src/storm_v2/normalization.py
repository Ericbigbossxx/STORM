"""Controlled normalizers with raw-value preservation and no silent fallback."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from .data_contract import MappingResult, MappingStatus


_WHITESPACE = re.compile(r"\s+")
_EXCEL_EPOCH = datetime(1899, 12, 30)


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value))
    text = _WHITESPACE.sub(" ", text).strip()
    return text or None


def normalize_sku(value: Any) -> str | None:
    """Trim/collapse whitespace and uppercase while preserving punctuation."""

    text = normalize_text(value)
    return text.upper() if text else None


def controlled_lookup(
    value: Any,
    aliases: Mapping[str, str],
    *,
    ambiguous_values: set[str] | None = None,
) -> MappingResult:
    raw = value
    normalized = normalize_text(value)
    if normalized is None:
        return MappingResult(raw, None, None, MappingStatus.UNMAPPED, "blank value")
    key = normalized.casefold()
    ambiguous = {item.casefold() for item in (ambiguous_values or set())}
    if key in ambiguous:
        return MappingResult(raw, normalized, None, MappingStatus.AMBIGUOUS, "context required")
    folded = {str(k).casefold(): v for k, v in aliases.items()}
    if key not in folded:
        return MappingResult(raw, normalized, None, MappingStatus.UNMAPPED, "no approved alias")
    return MappingResult(raw, normalized, folded[key], MappingStatus.MAPPED)


def normalize_date(value: Any) -> date | None:
    """Normalize supported Excel/string date values; unknown formats stay null."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            return (_EXCEL_EPOCH + timedelta(days=float(value))).date()
        except (OverflowError, ValueError):
            return None
    text = normalize_text(value)
    if text is None:
        return None
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%m/%d/%y", "%Y%m%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def as_number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = normalize_text(value)
    if not text or text.startswith("#"):
        return None
    cleaned = text.replace("$", "").replace(",", "").replace("%", "")
    try:
        return float(cleaned)
    except ValueError:
        return None
