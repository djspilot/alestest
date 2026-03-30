"""Unit tests for sheet-metal bending standards and calculations.

Tests every pure function in manufacturing_pipeline.analysis.sheetmetal.standards:
  - calculate_bend_allowance
  - calculate_bend_deduction
  - calculate_flat_length
  - get_minimum_bend_radius
  - recommend_v_opening
  - calculate_bend_force
  - BendSequenceOptimizer.suggest_sequence
  - calculate_complete_flat_pattern
  - Data-table invariants
"""
import math

import pytest

from manufacturing_pipeline.analysis.sheetmetal.standards import (
    K_FACTORS,
    MATERIAL_BEND_PROPERTIES,
    STANDARD_BEND_ANGLES,
    STANDARD_THICKNESSES,
    STANDARD_V_DIES,
    BendSequenceOptimizer,
    BendTool,
    calculate_bend_allowance,
    calculate_bend_deduction,
    calculate_bend_force,
    calculate_complete_flat_pattern,
    calculate_flat_length,
    get_minimum_bend_radius,
    recommend_v_opening,
)


# ===================================================================
# Data-table invariants
# ===================================================================


class TestStandardThicknesses:
    def test_sorted_ascending(self):
        assert STANDARD_THICKNESSES == sorted(STANDARD_THICKNESSES)

    def test_all_positive(self):
        assert all(t > 0 for t in STANDARD_THICKNESSES)

    def test_minimum_is_half_mm(self):
        assert STANDARD_THICKNESSES[0] == pytest.approx(0.5)

    def test_maximum_is_30mm(self):
        assert STANDARD_THICKNESSES[-1] == pytest.approx(30.0)

    def test_no_duplicates(self):
        assert len(STANDARD_THICKNESSES) == len(set(STANDARD_THICKNESSES))


class TestStandardBendAngles:
    def test_all_between_0_and_180(self):
        assert all(0 < a <= 180 for a in STANDARD_BEND_ANGLES)

    def test_includes_90(self):
        assert 90 in STANDARD_BEND_ANGLES


class TestStandardVDies:
    def test_all_keys_match_v_opening(self):
        for v_size, tool in STANDARD_V_DIES.items():
            assert tool.v_opening == v_size

    def test_max_thickness_positive(self):
        for v_size, tool in STANDARD_V_DIES.items():
            assert tool.max_thickness > 0

    def test_v_opening_at_least_4mm(self):
        assert min(STANDARD_V_DIES.keys()) >= 4

    def test_bendtool_is_frozen(self):
        tool = STANDARD_V_DIES[8]
        with pytest.raises(AttributeError):
            tool.name = "changed"


class TestKFactors:
    @pytest.mark.parametrize("material", ["steel", "stainless", "aluminum", "copper"])
    def test_has_required_methods(self, material):
        entry = K_FACTORS[material]
        for method in ("air_bend", "bottom_bend", "coining"):
            assert 0.0 < entry[method] < 1.0, f"{material}.{method} out of range"

    @pytest.mark.parametrize("material", ["steel", "stainless", "aluminum", "copper"])
    def test_air_bend_largest(self, material):
        """Air-bend K-factor should be the largest of the three methods."""
        entry = K_FACTORS[material]
        assert entry["air_bend"] > entry["bottom_bend"]
        assert entry["bottom_bend"] > entry["coining"]


class TestMaterialBendProperties:
    @pytest.mark.parametrize(
        "key",
        ["steel_s235", "steel_s355", "steel_304", "steel_316", "alu_5083", "alu_6082"],
    )
    def test_has_required_fields(self, key):
        props = MATERIAL_BEND_PROPERTIES[key]
        for field in ("name", "tensile_strength", "yield_strength", "k_factor",
                       "min_radius_factor", "springback_factor"):
            assert field in props, f"{key} missing {field}"

    @pytest.mark.parametrize("key", MATERIAL_BEND_PROPERTIES.keys())
    def test_tensile_greater_than_yield(self, key):
        props = MATERIAL_BEND_PROPERTIES[key]
        assert props["tensile_strength"] > props["yield_strength"]

    @pytest.mark.parametrize("key", MATERIAL_BEND_PROPERTIES.keys())
    def test_k_factor_in_valid_range(self, key):
        k = MATERIAL_BEND_PROPERTIES[key]["k_factor"]
        assert 0.0 < k < 1.0

    @pytest.mark.parametrize("key", MATERIAL_BEND_PROPERTIES.keys())
    def test_springback_factor_above_one(self, key):
        assert MATERIAL_BEND_PROPERTIES[key]["springback_factor"] > 1.0


# ===================================================================
# calculate_bend_allowance
# ===================================================================


class TestCalculateBendAllowance:
    def test_90_degrees_known_value(self):
        """BA for 90 deg, R=5, t=2, K=0.44 → π*(5+0.44*2)*90/180."""
        t, angle, r, k = 2.0, 90.0, 5.0, 0.44
        expected = math.pi * (r + k * t) * angle / 180.0
        result = calculate_bend_allowance(t, angle, r, k)
        assert result == pytest.approx(expected, rel=1e-10)

    def test_zero_angle_gives_zero(self):
        assert calculate_bend_allowance(2.0, 0.0, 5.0) == pytest.approx(0.0)

    def test_180_degrees(self):
        t, angle, r, k = 1.5, 180.0, 3.0, 0.44
        expected = math.pi * (r + k * t)  # * 180/180 = * 1
        assert calculate_bend_allowance(t, angle, r, k) == pytest.approx(expected)

    def test_increases_with_thickness(self):
        ba_thin = calculate_bend_allowance(1.0, 90.0, 5.0)
        ba_thick = calculate_bend_allowance(3.0, 90.0, 5.0)
        assert ba_thick > ba_thin

    def test_increases_with_radius(self):
        ba_small = calculate_bend_allowance(2.0, 90.0, 2.0)
        ba_large = calculate_bend_allowance(2.0, 90.0, 10.0)
        assert ba_large > ba_small

    def test_increases_with_angle(self):
        ba_45 = calculate_bend_allowance(2.0, 45.0, 5.0)
        ba_90 = calculate_bend_allowance(2.0, 90.0, 5.0)
        assert ba_90 == pytest.approx(2.0 * ba_45, rel=1e-10)

    def test_default_k_factor(self):
        """Default K=0.44 should match explicit call."""
        assert (calculate_bend_allowance(2.0, 90.0, 5.0)
                == pytest.approx(calculate_bend_allowance(2.0, 90.0, 5.0, 0.44)))


# ===================================================================
# calculate_bend_deduction
# ===================================================================


class TestCalculateBendDeduction:
    def test_90_degrees_known_value(self):
        t, angle, r, k = 2.0, 90.0, 5.0, 0.44
        ba = calculate_bend_allowance(t, angle, r, k)
        setback = (r + t) * math.tan(math.radians(angle / 2.0))
        expected = 2.0 * setback - ba
        assert calculate_bend_deduction(t, angle, r, k) == pytest.approx(expected)

    def test_zero_angle_gives_zero(self):
        assert calculate_bend_deduction(2.0, 0.0, 5.0) == pytest.approx(0.0)

    def test_deduction_positive_for_typical_bend(self):
        """For a typical 90-deg steel bend, BD should be positive."""
        bd = calculate_bend_deduction(2.0, 90.0, 5.0, 0.44)
        assert bd > 0

    def test_180_degrees(self):
        """At 180 deg the setback tangent is tan(90) = inf → very large BD."""
        bd = calculate_bend_deduction(2.0, 179.0, 5.0, 0.44)
        assert bd > 0

    def test_consistency_with_allowance(self):
        """BA and BD should satisfy: BD = 2*setback - BA."""
        t, angle, r, k = 3.0, 60.0, 4.0, 0.40
        ba = calculate_bend_allowance(t, angle, r, k)
        bd = calculate_bend_deduction(t, angle, r, k)
        setback = (r + t) * math.tan(math.radians(angle / 2.0))
        assert bd == pytest.approx(2.0 * setback - ba, rel=1e-10)


# ===================================================================
# calculate_flat_length
# ===================================================================


class TestCalculateFlatLength:
    def test_no_deduction_when_bd_zero(self):
        """If BD ≈ 0 (tiny angle), flat ≈ flange1 + flange2."""
        flat = calculate_flat_length(100.0, 80.0, 2.0, 0.01, 5.0)
        assert flat == pytest.approx(100.0 + 80.0, abs=0.1)

    def test_typical_90_deg(self):
        t, angle, r, k = 2.0, 90.0, 5.0, 0.44
        bd = calculate_bend_deduction(t, angle, r, k)
        expected = 100.0 + 80.0 - bd
        assert calculate_flat_length(100.0, 80.0, t, angle, r, k) == pytest.approx(expected)

    def test_flat_shorter_than_flange_sum(self):
        """Flat pattern must be shorter than the sum of flanges for positive BD."""
        flat = calculate_flat_length(100.0, 80.0, 2.0, 90.0, 5.0)
        assert flat < 100.0 + 80.0

    def test_flat_positive_for_reasonable_inputs(self):
        flat = calculate_flat_length(100.0, 80.0, 2.0, 90.0, 5.0)
        assert flat > 0


# ===================================================================
# get_minimum_bend_radius
# ===================================================================


class TestGetMinimumBendRadius:
    def test_steel(self):
        assert get_minimum_bend_radius(2.0, "steel") == pytest.approx(1.0)

    def test_stainless(self):
        assert get_minimum_bend_radius(2.0, "stainless") == pytest.approx(1.6)

    def test_aluminum_soft(self):
        assert get_minimum_bend_radius(2.0, "aluminum_soft") == pytest.approx(0.6)

    def test_aluminum_hard(self):
        assert get_minimum_bend_radius(2.0, "aluminum_hard") == pytest.approx(2.0)

    def test_copper(self):
        assert get_minimum_bend_radius(2.0, "copper") == pytest.approx(0.6)

    def test_brass(self):
        assert get_minimum_bend_radius(2.0, "brass") == pytest.approx(1.0)

    def test_unknown_material_uses_default(self):
        assert get_minimum_bend_radius(2.0, "titanium") == pytest.approx(1.0)  # 0.5 * 2.0

    def test_scales_with_thickness(self):
        r1 = get_minimum_bend_radius(1.0, "steel")
        r2 = get_minimum_bend_radius(3.0, "steel")
        assert r2 == pytest.approx(3.0 * r1)


# ===================================================================
# recommend_v_opening
# ===================================================================


class TestRecommendVOpening:
    def test_thin_sheet(self):
        """1mm sheet → target V=8, closest should be V8."""
        v_size, tool = recommend_v_opening(1.0)
        assert tool.max_thickness >= 1.0
        assert isinstance(tool, BendTool)

    def test_medium_sheet(self):
        v_size, tool = recommend_v_opening(3.0)
        assert tool.max_thickness >= 3.0

    def test_thick_sheet(self):
        v_size, tool = recommend_v_opening(10.0)
        assert tool.max_thickness >= 10.0

    def test_returns_tuple(self):
        result = recommend_v_opening(2.0)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_v_size_matches_tool(self):
        v_size, tool = recommend_v_opening(2.0)
        assert STANDARD_V_DIES[v_size] is tool

    def test_very_thin_sheet(self):
        """0.5mm should still get a valid die."""
        v_size, tool = recommend_v_opening(0.5)
        assert tool.max_thickness >= 0.5

    def test_very_thick_sheet(self):
        """30mm exceeds all V-die max_thickness → falls back to largest V-die."""
        v_size, tool = recommend_v_opening(30.0)
        # No die fits 30mm, so it returns the largest available (V80)
        assert v_size == 80

    def test_target_v_approximately_8x(self):
        """V-die should be close to 8 * thickness."""
        v_size, _ = recommend_v_opening(2.0)
        # target is 16mm, so V16 or nearby
        assert 8 <= v_size <= 24


# ===================================================================
# calculate_bend_force
# ===================================================================


class TestCalculateBendForce:
    def test_known_value(self):
        """F = 1.33 * 400 * 2² * 1000 / 16 / 1000."""
        force = calculate_bend_force(2.0, 1000.0, 16.0, 400.0)
        expected = 1.33 * 400 * 4 * 1000 / 16 / 1000
        assert force == pytest.approx(expected)

    def test_increases_with_thickness_squared(self):
        f1 = calculate_bend_force(1.0, 1000.0, 16.0)
        f4 = calculate_bend_force(4.0, 1000.0, 16.0)
        # thickness ratio = 4, force ratio ≈ 4² = 16
        assert f4 / f1 == pytest.approx(16.0, rel=1e-10)

    def test_increases_with_bend_length(self):
        f_short = calculate_bend_force(2.0, 500.0, 16.0)
        f_long = calculate_bend_force(2.0, 1000.0, 16.0)
        assert f_long == pytest.approx(2.0 * f_short)

    def test_decreases_with_v_opening(self):
        f_small_v = calculate_bend_force(2.0, 1000.0, 8.0)
        f_large_v = calculate_bend_force(2.0, 1000.0, 32.0)
        assert f_small_v > f_large_v

    def test_default_tensile_strength(self):
        force = calculate_bend_force(2.0, 1000.0, 16.0)
        expected = 1.33 * 400 * 4 * 1000 / 16 / 1000
        assert force == pytest.approx(expected)

    def test_result_positive(self):
        assert calculate_bend_force(2.0, 1000.0, 16.0, 400.0) > 0


# ===================================================================
# BendSequenceOptimizer
# ===================================================================


class TestBendSequenceOptimizer:
    def test_empty_input(self):
        assert BendSequenceOptimizer.suggest_sequence([]) == []

    def test_assigns_sequence_numbers(self):
        bends = [{"angle": 90, "min_flange": 20}]
        result = BendSequenceOptimizer.suggest_sequence(bends)
        assert result[0]["sequence"] == 1

    def test_sorts_by_shortest_flange_first(self):
        bends = [
            {"angle": 90, "min_flange": 30},
            {"angle": 90, "min_flange": 10},
            {"angle": 90, "min_flange": 20},
        ]
        result = BendSequenceOptimizer.suggest_sequence(bends)
        assert [b["min_flange"] for b in result] == [10, 20, 30]

    def test_steeper_angle_first_when_same_flange(self):
        bends = [
            {"angle": 90, "min_flange": 20},
            {"angle": 120, "min_flange": 20},
        ]
        result = BendSequenceOptimizer.suggest_sequence(bends)
        assert result[0]["angle"] == 120  # steeper first

    def test_notes_short_flange(self):
        bends = [{"angle": 90, "min_flange": 5}]
        result = BendSequenceOptimizer.suggest_sequence(bends)
        assert any("korte flens" in n for n in result[0]["notes"])

    def test_notes_steep_angle(self):
        bends = [{"angle": 135, "min_flange": 20}]
        result = BendSequenceOptimizer.suggest_sequence(bends)
        assert any("Scherpe hoek" in n for n in result[0]["notes"])

    def test_no_notes_for_normal_bend(self):
        bends = [{"angle": 90, "min_flange": 20}]
        result = BendSequenceOptimizer.suggest_sequence(bends)
        assert result[0]["notes"] == []

    def test_mutates_input_dicts(self):
        """suggest_sequence mutates in-place (documented behavior)."""
        bend = {"angle": 90, "min_flange": 20}
        BendSequenceOptimizer.suggest_sequence([bend])
        assert "sequence" in bend
        assert "notes" in bend

    def test_three_bends_sequenced(self):
        bends = [
            {"angle": 90, "min_flange": 25, "position_index": 0},
            {"angle": 60, "min_flange": 10, "position_index": 1},
            {"angle": 120, "min_flange": 10, "position_index": 2},
        ]
        result = BendSequenceOptimizer.suggest_sequence(bends)
        assert [b["sequence"] for b in result] == [1, 2, 3]
        # Shortest flange first, then steeper angle
        assert result[0]["position_index"] in (1, 2)


# ===================================================================
# calculate_complete_flat_pattern
# ===================================================================


class TestCalculateCompleteFlatPattern:
    def test_single_bend(self):
        result = calculate_complete_flat_pattern(
            flanges=[100.0, 80.0],
            bend_angles=[90.0],
            bend_radii=[5.0],
            thickness=2.0,
            k_factor=0.44,
        )
        assert "error" not in result
        assert result["flat_pattern_length"] > 0
        assert len(result["bend_details"]) == 1
        assert result["bend_details"][0]["bend_number"] == 1

    def test_two_bends(self):
        result = calculate_complete_flat_pattern(
            flanges=[100.0, 50.0, 80.0],
            bend_angles=[90.0, 90.0],
            bend_radii=[5.0, 5.0],
            thickness=2.0,
        )
        assert "error" not in result
        assert len(result["bend_details"]) == 2
        assert result["total_flange_length"] == pytest.approx(230.0)

    def test_too_few_flanges(self):
        result = calculate_complete_flat_pattern(
            flanges=[100.0],
            bend_angles=[],
            bend_radii=[],
            thickness=2.0,
        )
        assert "error" in result

    def test_angle_count_mismatch(self):
        result = calculate_complete_flat_pattern(
            flanges=[100.0, 80.0, 60.0],
            bend_angles=[90.0],  # need 2, got 1
            bend_radii=[5.0],
            thickness=2.0,
        )
        assert "error" in result

    def test_radii_count_mismatch(self):
        result = calculate_complete_flat_pattern(
            flanges=[100.0, 80.0],
            bend_angles=[90.0],
            bend_radii=[5.0, 3.0],  # need 1, got 2
            thickness=2.0,
        )
        assert "error" in result

    def test_flat_shorter_than_flange_sum(self):
        result = calculate_complete_flat_pattern(
            flanges=[100.0, 80.0],
            bend_angles=[90.0],
            bend_radii=[5.0],
            thickness=2.0,
        )
        assert result["flat_pattern_length"] < 180.0

    def test_deduction_consistency(self):
        """total_bend_deduction should equal sum of individual BDs."""
        result = calculate_complete_flat_pattern(
            flanges=[100.0, 60.0, 80.0],
            bend_angles=[90.0, 45.0],
            bend_radii=[5.0, 3.0],
            thickness=2.0,
        )
        bd_sum = sum(bd["bend_deduction"] for bd in result["bend_details"])
        assert result["total_bend_deduction"] == pytest.approx(bd_sum, abs=0.02)

    def test_formula_field_present(self):
        result = calculate_complete_flat_pattern(
            flanges=[100.0, 80.0],
            bend_angles=[90.0],
            bend_radii=[5.0],
            thickness=2.0,
        )
        assert "DIN 6935" in result["formula"]

    def test_returns_thickness_and_k_factor(self):
        result = calculate_complete_flat_pattern(
            flanges=[100.0, 80.0],
            bend_angles=[90.0],
            bend_radii=[5.0],
            thickness=3.0,
            k_factor=0.40,
        )
        assert result["thickness"] == 3.0
        assert result["k_factor"] == 0.40

    def test_zero_angle_no_deduction(self):
        """0-degree bend → BA=0, setback=0, BD=0 → flat = sum of flanges."""
        result = calculate_complete_flat_pattern(
            flanges=[100.0, 80.0],
            bend_angles=[0.0],
            bend_radii=[5.0],
            thickness=2.0,
        )
        assert result["total_bend_deduction"] == pytest.approx(0.0, abs=0.01)
        assert result["flat_pattern_length"] == pytest.approx(180.0, abs=0.01)
