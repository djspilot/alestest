from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from manufacturing_pipeline.analysis.part_analysis.rules import (
    classify_part_type,
    determine_unfold_reason,
)


class _PartType(Enum):
    PLAAT = "plaat"
    KOKER = "koker"
    HOEKPROFIEL = "hoekprofiel"
    U_PROFIEL = "u_profiel"
    C_PROFIEL = "c_profiel"
    BUIS = "buis"
    KOKER_PROFIEL = "koker_profiel"
    DRAAISTUK = "draaistuk"
    COMPLEX = "complex"
    OVERIG = "overig"


@dataclass
class _Bend:
    length: float


def _type_values() -> dict[str, _PartType]:
    return {item.name: item for item in _PartType}


def test_classify_part_type_turned_stock_becomes_buis() -> None:
    part_type, is_profile, bend_count_erp, reasons = classify_part_type(
        is_turned=True,
        is_sheet_metal=False,
        is_closed_profile=False,
        bend_count_total=0,
        length=500.0,
        width=40.0,
        height=40.0,
        bends=[],
        part_type_values=_type_values(),
    )

    assert part_type is _PartType.BUIS
    assert is_profile is True
    assert bend_count_erp == 0
    assert any(entry["step"] == "Profiel Type" for entry in reasons)


def test_classify_part_type_sheet_stock_profile_sets_zero_erp_bends() -> None:
    bends = [_Bend(length=950.0), _Bend(length=960.0)]
    part_type, is_profile, bend_count_erp, reasons = classify_part_type(
        is_turned=False,
        is_sheet_metal=True,
        is_closed_profile=False,
        bend_count_total=2,
        length=1000.0,
        width=50.0,
        height=20.0,
        bends=bends,
        part_type_values=_type_values(),
    )

    assert part_type is _PartType.U_PROFIEL
    assert is_profile is True
    assert bend_count_erp == 0
    assert any("ingekocht" in entry["conclusion"] for entry in reasons)


def test_determine_unfold_reason_profile_sheet_is_not_unfoldable() -> None:
    can_unfold, reason = determine_unfold_reason(
        is_sheet_metal=True,
        is_profile=True,
        bend_count_total=2,
        is_turned=False,
    )

    assert can_unfold is False
    assert "ingekocht" in reason


def test_determine_unfold_reason_sheet_with_bends_is_unfoldable() -> None:
    can_unfold, reason = determine_unfold_reason(
        is_sheet_metal=True,
        is_profile=False,
        bend_count_total=3,
        is_turned=False,
    )

    assert can_unfold is True
    assert "kan worden ontbogen" in reason
