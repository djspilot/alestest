"""Tests for profile routing."""
import pytest
from manufacturing_pipeline.analysis.router import RouteCategory, RouteResult, map_profile_label


def test_route_category_values():
    assert RouteCategory.PLAAT.value == "plaat"
    assert RouteCategory.PROFIEL.value == "profiel"
    assert RouteCategory.ROND.value == "rond"
    assert RouteCategory.OVERIG.value == "overig"


def test_route_category_has_four_members():
    assert len(RouteCategory) == 4

def test_map_plat_staal_to_plaat():
    result = map_profile_label("PLAT_STAAL", 0.98)
    assert result.category == RouteCategory.PLAAT


def test_map_i_family_to_profiel():
    result = map_profile_label("I_FAMILY", 0.90)
    assert result.category == RouteCategory.PROFIEL


def test_map_u_family_to_profiel():
    result = map_profile_label("U_FAMILY", 0.85)
    assert result.category == RouteCategory.PROFIEL


def test_map_l_family_to_profiel():
    result = map_profile_label("L_FAMILY", 0.85)
    assert result.category == RouteCategory.PROFIEL


def test_map_t_family_to_profiel():
    result = map_profile_label("T_FAMILY", 0.80)
    assert result.category == RouteCategory.PROFIEL


def test_map_rechthoekige_koker_to_profiel():
    result = map_profile_label("RECHTHOEKIGE_KOKER", 0.98)
    assert result.category == RouteCategory.PROFIEL


def test_map_rond_staal_to_rond():
    result = map_profile_label("ROND_STAAL", 0.99)
    assert result.category == RouteCategory.ROND


def test_map_ronde_buis_to_rond():
    result = map_profile_label("RONDE_BUIS", 0.99)
    assert result.category == RouteCategory.ROND


def test_map_anders_to_overig():
    result = map_profile_label("ANDERS", 0.60)
    assert result.category == RouteCategory.OVERIG


def test_map_unknown_label_to_overig():
    result = map_profile_label("SOMETHING_NEW", 0.50)
    assert result.category == RouteCategory.OVERIG


def test_route_result_has_profile_label():
    result = map_profile_label("ROND_STAAL", 0.99)
    assert result.profile_label == "ROND_STAAL"
    assert result.confidence == 0.99


def test_route_result_has_reasoning():
    result = map_profile_label("I_FAMILY", 0.90)
    assert len(result.reasoning) > 0
