from datetime import UTC, datetime

import pytest

from storm.domain.enums import Confidence, Health, HealthLevel
from storm.domain.ids import (
    is_storm_id,
    mint_action_id,
    mint_health_id,
    mint_signal_id,
    mint_sku_id,
    normalize_sku,
)
from storm.domain.models import (
    AdvisoryAssessment,
    BusinessHealthKey,
    CanonicalDimensions,
    HumanDecision,
)


def test_unknown_is_an_explicit_health_state() -> None:
    assert Health.UNKNOWN.value == "UNKNOWN"


def test_dimensions_require_market_and_platform_but_not_channel() -> None:
    dimensions = CanonicalDimensions(market="US", platform="walmart")
    assert dimensions.channel is None


def test_business_health_v0_1_accepts_only_platform_level_without_channel() -> None:
    key = BusinessHealthKey(week_id="2026-W32", market="US", platform="walmart")
    assert key.level is HealthLevel.PLATFORM
    assert key.channel is None

    with pytest.raises(ValueError, match="reserved"):
        BusinessHealthKey(
            week_id="2026-W32",
            market="US",
            platform="walmart",
            level=HealthLevel.CHANNEL,
        )

    with pytest.raises(ValueError, match="channel must be blank"):
        BusinessHealthKey(
            week_id="2026-W32",
            market="US",
            platform="walmart",
            channel="3P",
        )


def test_storm_ids_match_the_business_contract() -> None:
    values = {
        mint_health_id("2026-W32", "US", "WMT"): "HLT-2026W32-US-WMT",
        mint_sku_id("2026-W32", "US", "LOWES", "  s4 / kit "): "SKU-2026W32-US-LOWES-S4-KIT",
        mint_action_id("2026-W32", 7): "ACT-2026W32-7",
        mint_signal_id("2026-W32", 12): "SIG-2026W32-12",
    }
    for value, expected in values.items():
        assert value == expected
        assert is_storm_id(value)


def test_sku_and_sequence_inputs_are_validated() -> None:
    assert normalize_sku("a.b_c") == "A-B-C"
    with pytest.raises(ValueError):
        mint_action_id("2026-W32", 0)
    with pytest.raises(ValueError):
        mint_health_id("2026W32", "US", "WMT")


def test_ai_assessment_is_optional_and_does_not_contain_human_finality() -> None:
    assessment = AdvisoryAssessment()
    assert assessment.ai_analysis is None
    assert not hasattr(assessment, "human_decision")

    populated = AdvisoryAssessment("Evidence is incomplete", "UNKNOWN", Confidence.LOW)
    assert populated.ai_confidence is Confidence.LOW


def test_reviewed_human_decision_requires_timestamp() -> None:
    with pytest.raises(ValueError):
        HumanDecision(decision="VALIDATED_EFFECTIVE", reviewed=True)

    decision = HumanDecision(
        decision="VALIDATED_EFFECTIVE",
        reviewed=True,
        reviewed_at=datetime.now(UTC),
    )
    assert decision.reviewed
