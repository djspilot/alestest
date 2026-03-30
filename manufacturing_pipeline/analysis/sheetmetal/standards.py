from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


STANDARD_THICKNESSES = [
    0.5,
    0.6,
    0.7,
    0.8,
    0.9,
    1.0,
    1.2,
    1.5,
    1.8,
    2.0,
    2.5,
    3.0,
    4.0,
    5.0,
    6.0,
    8.0,
    10.0,
    12.0,
    15.0,
    20.0,
    25.0,
    30.0,
]

STANDARD_BEND_ANGLES = [30, 45, 60, 90, 120, 135, 150, 180]


@dataclass
class BendTool:
    name: str
    v_opening: float
    punch_radius: float
    max_thickness: float
    min_flange: float
    tonnage_per_m: float


STANDARD_V_DIES = {
    4: BendTool("V4", 4, 0.5, 0.5, 4, 8),
    6: BendTool("V6", 6, 0.8, 0.8, 5, 12),
    8: BendTool("V8", 8, 1.0, 1.0, 6, 18),
    10: BendTool("V10", 10, 1.2, 1.5, 8, 25),
    12: BendTool("V12", 12, 1.5, 2.0, 10, 35),
    16: BendTool("V16", 16, 2.0, 2.5, 12, 50),
    20: BendTool("V20", 20, 2.5, 3.0, 15, 70),
    24: BendTool("V24", 24, 3.0, 4.0, 18, 90),
    32: BendTool("V32", 32, 4.0, 5.0, 24, 130),
    40: BendTool("V40", 40, 5.0, 6.0, 30, 180),
    50: BendTool("V50", 50, 6.0, 8.0, 38, 250),
    63: BendTool("V63", 63, 8.0, 10.0, 48, 350),
    80: BendTool("V80", 80, 10.0, 12.0, 60, 500),
}


K_FACTORS = {
    "steel": {
        "air_bend": 0.44,
        "bottom_bend": 0.33,
        "coining": 0.25,
    },
    "stainless": {
        "air_bend": 0.45,
        "bottom_bend": 0.34,
        "coining": 0.26,
    },
    "aluminum": {
        "air_bend": 0.40,
        "bottom_bend": 0.30,
        "coining": 0.22,
    },
    "copper": {
        "air_bend": 0.38,
        "bottom_bend": 0.28,
        "coining": 0.20,
    },
}


def calculate_bend_allowance(
    thickness: float,
    bend_angle: float,
    inner_radius: float,
    k_factor: float = 0.44,
) -> float:
    return math.pi * (inner_radius + k_factor * thickness) * bend_angle / 180


def calculate_bend_deduction(
    thickness: float,
    bend_angle: float,
    inner_radius: float,
    k_factor: float = 0.44,
) -> float:
    ba = calculate_bend_allowance(thickness, bend_angle, inner_radius, k_factor)
    setback = (inner_radius + thickness) * math.tan(math.radians(bend_angle / 2))
    return 2 * setback - ba


def calculate_flat_length(
    flange1: float,
    flange2: float,
    thickness: float,
    bend_angle: float,
    inner_radius: float,
    k_factor: float = 0.44,
) -> float:
    bd = calculate_bend_deduction(thickness, bend_angle, inner_radius, k_factor)
    return flange1 + flange2 - bd


def get_minimum_bend_radius(thickness: float, material: str = "steel") -> float:
    factors = {
        "steel": 0.5,
        "stainless": 0.8,
        "aluminum_soft": 0.3,
        "aluminum_hard": 1.0,
        "copper": 0.3,
        "brass": 0.5,
    }
    return thickness * factors.get(material, 0.5)


def recommend_v_opening(thickness: float) -> Tuple[int, BendTool]:
    target_v = thickness * 8
    best_v = None
    for v_size, tool in STANDARD_V_DIES.items():
        if tool.max_thickness >= thickness:
            if best_v is None or abs(v_size - target_v) < abs(best_v - target_v):
                best_v = v_size

    if best_v is None:
        best_v = max(STANDARD_V_DIES.keys())

    return best_v, STANDARD_V_DIES[best_v]


def calculate_bend_force(
    thickness: float,
    bend_length: float,
    v_opening: float,
    tensile_strength: float = 400,
) -> float:
    force_n = (1.33 * tensile_strength * thickness**2 * bend_length) / v_opening
    return force_n / 1000


MATERIAL_BEND_PROPERTIES = {
    "steel_s235": {
        "name": "S235JR",
        "tensile_strength": 360,
        "yield_strength": 235,
        "k_factor": 0.44,
        "min_radius_factor": 0.5,
        "springback_factor": 1.02,
    },
    "steel_s355": {
        "name": "S355J2",
        "tensile_strength": 510,
        "yield_strength": 355,
        "k_factor": 0.44,
        "min_radius_factor": 0.6,
        "springback_factor": 1.03,
    },
    "steel_304": {
        "name": "RVS 304",
        "tensile_strength": 520,
        "yield_strength": 210,
        "k_factor": 0.45,
        "min_radius_factor": 0.8,
        "springback_factor": 1.04,
    },
    "steel_316": {
        "name": "RVS 316",
        "tensile_strength": 530,
        "yield_strength": 220,
        "k_factor": 0.45,
        "min_radius_factor": 0.8,
        "springback_factor": 1.04,
    },
    "alu_5083": {
        "name": "Aluminium 5083-H111",
        "tensile_strength": 275,
        "yield_strength": 125,
        "k_factor": 0.40,
        "min_radius_factor": 1.0,
        "springback_factor": 1.05,
    },
    "alu_6082": {
        "name": "Aluminium 6082-T6",
        "tensile_strength": 310,
        "yield_strength": 260,
        "k_factor": 0.40,
        "min_radius_factor": 1.5,
        "springback_factor": 1.06,
    },
}


class BendSequenceOptimizer:
    @staticmethod
    def suggest_sequence(bends: List[Dict]) -> List[Dict]:
        if not bends:
            return []

        sorted_bends = sorted(
            bends,
            key=lambda b: (
                b.get("min_flange", 0),
                -b.get("angle", 90),
                b.get("position_index", 0),
            ),
        )

        for i, bend in enumerate(sorted_bends):
            bend["sequence"] = i + 1
            bend["notes"] = []
            if bend.get("min_flange", 100) < 8:
                bend["notes"].append("Let op: korte flens, gebruik precisie-aanslag")
            if bend.get("angle", 90) > 120:
                bend["notes"].append("Scherpe hoek: mogelijk 2 buigingen nodig")

        return sorted_bends


def calculate_complete_flat_pattern(
    flanges: List[float],
    bend_angles: List[float],
    bend_radii: List[float],
    thickness: float,
    k_factor: float = 0.44,
) -> Dict[str, Any]:
    if len(flanges) < 2 or len(bend_angles) != len(flanges) - 1:
        return {"error": "Invalid input: need at least 2 flanges and matching bend angles"}

    total_deduction = 0.0
    bend_details = []

    for i, (angle, radius) in enumerate(zip(bend_angles, bend_radii)):
        ba = calculate_bend_allowance(thickness, angle, radius, k_factor)
        bd = calculate_bend_deduction(thickness, angle, radius, k_factor)
        total_deduction += bd
        bend_details.append(
            {
                "bend_number": i + 1,
                "angle": angle,
                "radius": radius,
                "bend_allowance": round(ba, 2),
                "bend_deduction": round(bd, 2),
            }
        )

    flat_length = sum(flanges) - total_deduction
    return {
        "flanges": flanges,
        "total_flange_length": round(sum(flanges), 2),
        "total_bend_deduction": round(total_deduction, 2),
        "flat_pattern_length": round(flat_length, 2),
        "thickness": thickness,
        "k_factor": k_factor,
        "bend_details": bend_details,
        "formula": "Flat = ΣFlanges - ΣBend_Deductions (DIN 6935)",
    }
