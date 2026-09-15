"""Immutable, machine-minted STORM identifier helpers."""

import re


_WEEK_ID_PATTERN = re.compile(r"^(?P<year>\d{4})-W(?P<week>0[1-9]|[1-4]\d|5[0-3])$")
_CODE_PATTERN = re.compile(r"^[A-Z0-9]+$")
_SKU_SEPARATOR_PATTERN = re.compile(r"[^A-Z0-9]+")
_STORM_ID_PATTERNS = (
    re.compile(r"^HLT-\d{4}W\d{2}-[A-Z0-9]+-[A-Z0-9]+$"),
    re.compile(r"^SKU-\d{4}W\d{2}-[A-Z0-9]+-[A-Z0-9]+-[A-Z0-9]+(?:-[A-Z0-9]+)*$"),
    re.compile(r"^(?:ACT|SIG)-\d{4}W\d{2}-[1-9]\d*$"),
)


def _week_token(week_id: str) -> str:
    match = _WEEK_ID_PATTERN.fullmatch(week_id.strip())
    if match is None:
        raise ValueError("week_id must use YYYY-Www")
    return f"{match.group('year')}W{match.group('week')}"


def _code(value: str, field_name: str) -> str:
    normalized = value.strip().upper()
    if not _CODE_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must contain only A-Z and 0-9")
    return normalized


def normalize_sku(value: str) -> str:
    """Normalize a source SKU for use in the stable Core SKU identifier."""

    normalized = _SKU_SEPARATOR_PATTERN.sub("-", value.strip().upper()).strip("-")
    if not normalized:
        raise ValueError("sku must contain at least one letter or number")
    return normalized


def mint_health_id(week_id: str, market: str, platform_code: str) -> str:
    return f"HLT-{_week_token(week_id)}-{_code(market, 'market')}-{_code(platform_code, 'platform_code')}"


def mint_sku_id(week_id: str, market: str, platform_code: str, sku: str) -> str:
    return (
        f"SKU-{_week_token(week_id)}-{_code(market, 'market')}-"
        f"{_code(platform_code, 'platform_code')}-{normalize_sku(sku)}"
    )


def _mint_sequence_id(prefix: str, week_id: str, sequence: int) -> str:
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ValueError("sequence must be a positive machine-allocated integer")
    return f"{prefix}-{_week_token(week_id)}-{sequence}"


def mint_action_id(week_id: str, sequence: int) -> str:
    return _mint_sequence_id("ACT", week_id, sequence)


def mint_signal_id(week_id: str, sequence: int) -> str:
    return _mint_sequence_id("SIG", week_id, sequence)


def is_storm_id(value: str) -> bool:
    """Return whether a value conforms to one of the v0.1 ID formats."""

    return any(pattern.fullmatch(value) for pattern in _STORM_ID_PATTERNS)
