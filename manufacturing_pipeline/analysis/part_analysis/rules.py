from __future__ import annotations

from typing import Any, Mapping


def _is_likely_stock_profile(
    *,
    bend_count_total: int,
    length: float,
    width: float,
    height: float,
    bends: list[Any],
) -> tuple[bool, float]:
    if bend_count_total not in (1, 2, 3):
        return False, 0.0

    aspect_ratio_len = length / width if width > 0 else 0.0
    if aspect_ratio_len <= 3.0:
        return False, aspect_ratio_len

    all_long_bends = all(float(getattr(b, "length", 0.0)) > length * 0.9 for b in bends)
    standard_dims = [10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 100, 120, 150, 200]
    is_standard_w = any(abs(width - value) < 0.5 for value in standard_dims)
    is_standard_h = any(abs(height - value) < 0.5 for value in standard_dims)
    is_likely_stock = all_long_bends and (is_standard_w or is_standard_h)
    return is_likely_stock, aspect_ratio_len


def classify_part_type(
    *,
    is_turned: bool,
    is_sheet_metal: bool,
    is_closed_profile: bool,
    bend_count_total: int,
    length: float,
    width: float,
    height: float,
    bends: list[Any],
    part_type_values: Mapping[str, Any],
) -> tuple[Any, bool, int, list[dict[str, Any]]]:
    """Return (part_type, is_profile, bend_count_erp, reasoning_entries)."""
    is_profile = False
    part_type = part_type_values["OVERIG"]
    bend_count_erp = bend_count_total
    reasoning_entries: list[dict[str, Any]] = []

    if is_turned:
        diameter = max(width, height)
        aspect_ratio = length / diameter if diameter > 0 else 0.0
        if aspect_ratio > 4.0:
            part_type = part_type_values["BUIS"]
            is_profile = True
            reasoning_entries.append(
                {
                    "step": "Profiel Type",
                    "observation": f"Cilindrisch met aspect ratio {aspect_ratio:.1f}",
                    "conclusion": "BUIS/STAF - ingekocht profiel",
                    "details": {"aspect_ratio": aspect_ratio},
                }
            )
        else:
            part_type = part_type_values["DRAAISTUK"]
        return part_type, is_profile, bend_count_erp, reasoning_entries

    if is_sheet_metal:
        if is_closed_profile:
            part_type = part_type_values["KOKER"]
            is_profile = True
            bend_count_erp = 0
            reasoning_entries.append(
                {
                    "step": "Profiel Type",
                    "observation": f"Gesloten profiel met {bend_count_total} zettingen",
                    "conclusion": "KOKER PROFIEL - ingekocht, 0 zettingen voor ERP",
                    "details": {},
                }
            )
            return part_type, is_profile, bend_count_erp, reasoning_entries

        if bend_count_total == 0:
            part_type = part_type_values["PLAAT"]
            return part_type, is_profile, bend_count_erp, reasoning_entries

        if bend_count_total in (1, 2, 3):
            if bend_count_total == 1:
                part_type = part_type_values["HOEKPROFIEL"]
            elif bend_count_total == 2:
                part_type = part_type_values["U_PROFIEL"]
            else:
                part_type = part_type_values["C_PROFIEL"]

            is_likely_stock, aspect_ratio_len = _is_likely_stock_profile(
                bend_count_total=bend_count_total,
                length=length,
                width=width,
                height=height,
                bends=bends,
            )
            if is_likely_stock:
                is_profile = True
                bend_count_erp = 0
                reasoning_entries.append(
                    {
                        "step": "Profiel Type",
                        "observation": (
                            f"{part_type.value} met aspect ratio {aspect_ratio_len:.1f}, "
                            "bends over volle lengte en standaard afmetingen"
                        ),
                        "conclusion": f"{part_type.value.upper()} PROFIEL (ingekocht) - 0 zettingen voor ERP",
                        "details": {
                            "aspect_ratio": aspect_ratio_len,
                            "width": width,
                            "height": height,
                        },
                    }
                )
            return part_type, is_profile, bend_count_erp, reasoning_entries

        part_type = part_type_values["COMPLEX"]
        return part_type, is_profile, bend_count_erp, reasoning_entries

    aspect_ratio = length / width if width > 0 else 0.0
    if aspect_ratio > 5:
        is_profile = True
        part_type = part_type_values["KOKER_PROFIEL"]
        reasoning_entries.append(
            {
                "step": "Profiel Type",
                "observation": f"Aspect ratio {aspect_ratio:.1f} (lengte/breedte > 5)",
                "conclusion": "Langwerpig PROFIEL - waarschijnlijk ingekocht",
                "details": {"aspect_ratio": aspect_ratio},
            }
        )

    return part_type, is_profile, bend_count_erp, reasoning_entries


def determine_unfold_reason(
    *,
    is_sheet_metal: bool,
    is_profile: bool,
    bend_count_total: int,
    is_turned: bool,
) -> tuple[bool, str]:
    if is_sheet_metal:
        if is_profile:
            return False, "Profiel - ingekocht, geen ontbuigen nodig"
        if bend_count_total == 0:
            return False, "Vlakke plaat - geen buigingen om te ontbuigen"
        return True, f"Plaatwerk met {bend_count_total} zettingen - kan worden ontbogen"

    if is_turned:
        return False, "Draaistuk - geen plaatwerk"

    return False, "Geen plaatwerk gedetecteerd"
