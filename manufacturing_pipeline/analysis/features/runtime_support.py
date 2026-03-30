from __future__ import annotations


class _IsoThreadMatch:
    def __init__(self, designation: str = "", pitch: float = 0.0, major_diameter: float = 0.0):
        self.designation = designation
        self.pitch = pitch
        self.major_diameter = major_diameter


class _IsoStandardsFallback:
    """Minimal compatibility shim after removing analysis/iso_standards.py."""

    @staticmethod
    def analyze_hole_fit(_diameter):
        recommendation = {"fit": "N/A", "description": "ISO disabled"}
        return {
            "primary_recommendation": recommendation,
            "alternative_recommendation": recommendation,
            "tolerances": {},
        }

    @staticmethod
    def identify_thread_from_diameter(_diameter, _tolerance=0.15):
        return []

    @staticmethod
    def get_tap_drill_size(_designation):
        return None

    @staticmethod
    def get_nearest_standard_fillet(value):
        return value

    @staticmethod
    def get_nearest_standard_chamfer(value):
        return value

    @staticmethod
    def recommend_iso2768_class(_part_type, _complexity):
        return "m", "K"

    @staticmethod
    def get_iso2768_linear_tolerance(_dimension, _linear_class):
        return 0.0

    @staticmethod
    def analyze_surface_requirements(_face_analysis):
        return {
            "default_ra": 3.2,
            "general_recommendation": "ISO disabled",
            "by_face_type": [],
        }

    @staticmethod
    def calculate_mass(volume_mm3, material_key="steel_s235"):
        density = 7.85e-6 if material_key.startswith("steel") else 2.70e-6
        mass_kg = float(volume_mm3 or 0.0) * density
        return {
            "material": material_key,
            "mass_kg": mass_kg,
            "density_kg_m3": density * 1e9,
        }

    @staticmethod
    def get_all_materials_by_category():
        return {"steel": ["steel_s235"], "aluminum": ["alu_6061"]}


class _WerkvoorbereidingFallback:
    @staticmethod
    def calculate_cost_estimate(*_args, **_kwargs):
        return {"estimated_total_cost": None, "currency": "EUR"}

    @staticmethod
    def generate_tool_list(*_args, **_kwargs):
        return []

    @staticmethod
    def classify_outsourcing(*_args, **_kwargs):
        return {"recommended": False, "reason": "Werkvoorbereiding disabled"}

    @staticmethod
    def recommend_surface_treatment(*_args, **_kwargs):
        return []

    @staticmethod
    def generate_purchase_spec(*_args, **_kwargs):
        return {"summary": "Werkvoorbereiding disabled"}
