from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class IsoThreadMatch:
    designation: str
    pitch: float
    major_diameter: float
    minor_diameter: float
    tap_drill: float
    is_coarse: bool = True


class IsoStandards:
    """Compact ISO provider with metric thread tables for runtime detection."""

    _THREADS: List[Dict[str, float]] = [
        {"designation": "M3", "pitch": 0.5, "major": 3.0, "tap": 2.5},
        {"designation": "M4", "pitch": 0.7, "major": 4.0, "tap": 3.3},
        {"designation": "M5", "pitch": 0.8, "major": 5.0, "tap": 4.2},
        {"designation": "M6", "pitch": 1.0, "major": 6.0, "tap": 5.0},
        {"designation": "M8", "pitch": 1.25, "major": 8.0, "tap": 6.8},
        {"designation": "M10", "pitch": 1.5, "major": 10.0, "tap": 8.5},
        {"designation": "M12", "pitch": 1.75, "major": 12.0, "tap": 10.2},
        {"designation": "M14", "pitch": 2.0, "major": 14.0, "tap": 12.0},
        {"designation": "M16", "pitch": 2.0, "major": 16.0, "tap": 14.0},
        {"designation": "M18", "pitch": 2.5, "major": 18.0, "tap": 15.5},
        {"designation": "M20", "pitch": 2.5, "major": 20.0, "tap": 17.5},
        {"designation": "M22", "pitch": 2.5, "major": 22.0, "tap": 19.5},
        {"designation": "M24", "pitch": 3.0, "major": 24.0, "tap": 21.0},
    ]

    _FILLETS = [0.2, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0]
    _CHAMFERS = [0.2, 0.3, 0.5, 1.0, 1.5, 2.0, 3.0]
    _MATERIAL_DENSITY_KG_PER_MM3 = {
        "steel_s235": 7.85e-6,
        "steel_s275": 7.85e-6,
        "steel_s355": 7.85e-6,
        "stainless_304": 7.90e-6,
        "stainless_316": 8.00e-6,
        "alu_6061": 2.70e-6,
        "alu_6082": 2.70e-6,
    }

    def identify_thread_from_diameter(self, diameter: float, tolerance: float = 0.15) -> List[IsoThreadMatch]:
        d = float(diameter)
        matches: List[Tuple[float, IsoThreadMatch]] = []

        for row in self._THREADS:
            major = float(row["major"])
            tap = float(row["tap"])
            pitch = float(row["pitch"])
            designation = str(row["designation"])
            minor = major - (1.22687 * pitch)

            major_delta = abs(d - major)
            if major_delta <= tolerance:
                matches.append(
                    (
                        major_delta,
                        IsoThreadMatch(
                            designation=designation,
                            pitch=pitch,
                            major_diameter=major,
                            minor_diameter=minor,
                            tap_drill=tap,
                            is_coarse=True,
                        ),
                    )
                )

            tap_delta = abs(d - tap)
            if tap_delta <= tolerance:
                matches.append(
                    (
                        tap_delta,
                        IsoThreadMatch(
                            designation=f"{designation} tapped",
                            pitch=pitch,
                            major_diameter=major,
                            minor_diameter=minor,
                            tap_drill=tap,
                            is_coarse=True,
                        ),
                    )
                )

        matches.sort(key=lambda item: item[0])
        return [match for _, match in matches]

    def get_tap_drill_size(self, designation: str):
        key = str(designation).strip().upper().replace("(TAPPED)", "").replace("TAPPED", "").strip()
        for row in self._THREADS:
            if str(row["designation"]).upper() == key:
                return float(row["tap"])
        return None

    def analyze_hole_fit(self, diameter: float):
        d = float(diameter)
        if d < 3.0:
            fit = {"fit": "H7/h6", "description": "Precision running fit"}
        elif d < 12.0:
            fit = {"fit": "H8/f7", "description": "Sliding fit"}
        else:
            fit = {"fit": "H11/c11", "description": "Loose fit"}
        return {
            "primary_recommendation": fit,
            "alternative_recommendation": fit,
            "tolerances": {},
        }

    def get_nearest_standard_fillet(self, value: float):
        v = float(value)
        return min(self._FILLETS, key=lambda x: abs(x - v))

    def get_nearest_standard_chamfer(self, value: float):
        v = float(value)
        return min(self._CHAMFERS, key=lambda x: abs(x - v))

    def recommend_iso2768_class(self, _part_type: str, complexity: float):
        c = float(complexity)
        if c >= 0.75:
            return "f", "H"
        if c >= 0.35:
            return "m", "K"
        return "c", "L"

    def get_iso2768_linear_tolerance(self, dimension: float, linear_class: str):
        d = abs(float(dimension))
        table = {
            "f": [(3, 0.05), (6, 0.05), (30, 0.10), (120, 0.15), (400, 0.20), (1000, 0.30), (999999, 0.50)],
            "m": [(3, 0.10), (6, 0.10), (30, 0.20), (120, 0.30), (400, 0.50), (1000, 0.80), (999999, 1.20)],
            "c": [(3, 0.20), (6, 0.30), (30, 0.50), (120, 0.80), (400, 1.20), (1000, 2.00), (999999, 3.00)],
            "v": [(3, 0.50), (6, 1.00), (30, 1.50), (120, 2.50), (400, 4.00), (1000, 6.00), (999999, 8.00)],
        }
        rows = table.get(str(linear_class).lower(), table["m"])
        for limit, tol in rows:
            if d <= limit:
                return tol
        return rows[-1][1]

    def analyze_surface_requirements(self, _face_analysis):
        return {
            "default_ra": 3.2,
            "general_recommendation": "General machining finish",
            "by_face_type": [],
        }

    def calculate_mass(self, volume_mm3: float, material_key: str = "steel_s235"):
        density = self._MATERIAL_DENSITY_KG_PER_MM3.get(material_key, self._MATERIAL_DENSITY_KG_PER_MM3["steel_s235"])
        mass_kg = float(volume_mm3 or 0.0) * density
        return {
            "material": material_key,
            "mass_kg": mass_kg,
            "density_kg_m3": density * 1e9,
        }

    def get_all_materials_by_category(self):
        return {
            "steel": ["steel_s235", "steel_s275", "steel_s355", "stainless_304", "stainless_316"],
            "aluminum": ["alu_6061", "alu_6082"],
        }
