"""
Werkvoorbereiding Module - Manufacturing Preparation Automation

Automates key tasks typically performed by a werkvoorbereider (manufacturing engineer):
- Cost estimation (bewerkingstijd, materiaalkosten, uurtarieven)
- Tool list generation (gereedschapslijst)
- Outsourcing classification (uitbesteding routing)
- Surface treatment recommendations (oppervlaktebehandeling)
- Material purchasing specs (inkoop specificaties)

Based on Dutch/European manufacturing standards and practices.
"""

import math
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


# =============================================================================
# UURTARIEVEN / HOURLY RATES (Nederlandse markt, 2024)
# =============================================================================

HOURLY_RATES = {
    # CNC bewerkingen
    "cnc_draaien_klein": 55.0,      # < Ø100mm
    "cnc_draaien_middel": 65.0,     # Ø100-300mm
    "cnc_draaien_groot": 85.0,      # > Ø300mm
    "cnc_frezen_3as": 60.0,
    "cnc_frezen_4as": 75.0,
    "cnc_frezen_5as": 95.0,

    # Plaatwerk
    "laser_snijden": 70.0,
    "plasma_snijden": 55.0,
    "waterstraal": 85.0,
    "ponsen": 50.0,
    "kanten": 45.0,              # Zetbank
    "lassen_mig": 50.0,
    "lassen_tig": 65.0,

    # Nabewerking
    "slijpen_vlak": 55.0,
    "slijpen_rond": 60.0,
    "honen": 70.0,
    "polijsten": 45.0,
    "ontbramen_hand": 35.0,
    "ontbramen_machine": 40.0,

    # Oppervlaktebehandeling
    "stralen": 40.0,
    "lakken_poeder": 45.0,
    "lakken_nat": 50.0,
    "verzinken": 35.0,          # Per kg basis
    "anodiseren": 55.0,
    "verchromen": 75.0,
    "nitreren": 65.0,

    # Setup / insteltijd
    "setup_eenvoudig": 0.5,     # uren
    "setup_gemiddeld": 1.0,
    "setup_complex": 2.0,
    "setup_5as": 3.0,
}


# =============================================================================
# MATERIAAL PRIJZEN (indicatief, €/kg)
# =============================================================================

MATERIAL_PRICES = {
    # Staal
    "steel_s235": {"price_kg": 1.20, "name": "S235JR Constructiestaal"},
    "steel_s355": {"price_kg": 1.35, "name": "S355J2 Constructiestaal"},
    "steel_304": {"price_kg": 4.50, "name": "RVS 304 (1.4301)"},
    "steel_316": {"price_kg": 5.80, "name": "RVS 316 (1.4404)"},
    "steel_42crmo4": {"price_kg": 2.20, "name": "42CrMo4 Machinebouwstaal"},
    "steel_c45": {"price_kg": 1.80, "name": "C45 Machinebouwstaal"},

    # Aluminium
    "alu_6061": {"price_kg": 3.50, "name": "6061-T6 Constructie"},
    "alu_6082": {"price_kg": 3.80, "name": "6082-T6 Constructie"},
    "alu_7075": {"price_kg": 8.50, "name": "7075-T6 Luchtvaart"},
    "alu_5083": {"price_kg": 4.20, "name": "5083-H111 Maritiem"},

    # Kunststof
    "pom": {"price_kg": 4.50, "name": "POM (Delrin)"},
    "peek": {"price_kg": 85.0, "name": "PEEK"},
    "nylon_pa6": {"price_kg": 5.50, "name": "PA6 Nylon"},
    "ptfe": {"price_kg": 25.0, "name": "PTFE (Teflon)"},

    # Koper/Messing
    "messing_cuzn39pb3": {"price_kg": 7.50, "name": "Messing CuZn39Pb3"},
    "brons_cusn8": {"price_kg": 12.0, "name": "Brons CuSn8"},
}


# =============================================================================
# GEREEDSCHAP DATABASE
# =============================================================================

class ToolType(Enum):
    DRILL = "boor"
    TAP = "tap"
    ENDMILL = "vingerfrees"
    FACEMILL = "vlakfrees"
    TURNING_INSERT = "wisselplaat_draaien"
    BORING_BAR = "kotterbeitel"
    REAMER = "ruimer"
    CHAMFER = "verzinkboor"
    THREADMILL = "draadfrezen"


@dataclass
class Tool:
    """Gereedschap definitie"""
    tool_type: ToolType
    designation: str           # bijv. "Ø8 HSS boor" of "M6 tap"
    diameter: float           # mm
    description: str
    cutting_speed: float      # m/min (aanbevolen)
    feed_per_tooth: float     # mm/tand of mm/omw
    typical_cost: float       # € indicatief


# Standaard gereedschappen per feature
TOOL_DATABASE = {
    # Boren (HSS voor algemeen, VHM voor nauwkeurig)
    "drill_hss": lambda d: Tool(
        ToolType.DRILL, f"Ø{d} HSS boor", d,
        f"HSS spiraalboor Ø{d}mm DIN 338",
        cutting_speed=25.0, feed_per_tooth=0.02 * d, typical_cost=5.0 + d * 0.5
    ),
    "drill_vhm": lambda d: Tool(
        ToolType.DRILL, f"Ø{d} VHM boor", d,
        f"Volhardmetaal spiraalboor Ø{d}mm",
        cutting_speed=80.0, feed_per_tooth=0.015 * d, typical_cost=25.0 + d * 2.0
    ),

    # Tappen
    "tap_hss": lambda m, p: Tool(
        ToolType.TAP, f"M{m}x{p} tap", m,
        f"HSS machinetap M{m}x{p} DIN 371",
        cutting_speed=12.0, feed_per_tooth=p, typical_cost=15.0 + m * 1.5
    ),

    # Ruimers
    "reamer": lambda d: Tool(
        ToolType.REAMER, f"Ø{d} ruimer", d,
        f"HSS machineruimer Ø{d}mm H7",
        cutting_speed=8.0, feed_per_tooth=0.1, typical_cost=30.0 + d * 3.0
    ),

    # Frezen
    "endmill_hss": lambda d: Tool(
        ToolType.ENDMILL, f"Ø{d} HSS frees", d,
        f"HSS vingerfrees Ø{d}mm 4-snijder",
        cutting_speed=30.0, feed_per_tooth=0.02, typical_cost=15.0 + d * 1.0
    ),
    "endmill_vhm": lambda d: Tool(
        ToolType.ENDMILL, f"Ø{d} VHM frees", d,
        f"Volhardmetaal vingerfrees Ø{d}mm",
        cutting_speed=150.0, feed_per_tooth=0.05, typical_cost=45.0 + d * 4.0
    ),
}


# =============================================================================
# UITBESTEDING CLASSIFICATIE
# =============================================================================

class OutsourceCategory(Enum):
    INTERNAL = "intern"
    CNC_DRAAIEN = "cnc_draaierij"
    CNC_FREZEN = "cnc_frezerij"
    PLAATWERK = "plaatwerker"
    VERSPANING_5AS = "5-assig_freeswerk"
    SLIJPEN = "slijperij"
    WARMTEBEHANDELING = "warmtebehandeling"
    OPPERVLAKTEBEHANDELING = "oppervlaktebehandeling"
    LASSEN = "lasbedrijf"
    DRAADVONKEN = "vonkerij"
    THREE_D_PRINT = "3d_print"
    GIETEN = "gieterij"


OUTSOURCE_SUPPLIERS = {
    OutsourceCategory.CNC_DRAAIEN: {
        "typical_lead_time": "5-10 werkdagen",
        "min_order": "€50",
        "certifications": ["ISO 9001"],
    },
    OutsourceCategory.CNC_FREZEN: {
        "typical_lead_time": "5-10 werkdagen",
        "min_order": "€75",
        "certifications": ["ISO 9001"],
    },
    OutsourceCategory.PLAATWERK: {
        "typical_lead_time": "3-7 werkdagen",
        "min_order": "€25",
        "certifications": ["ISO 9001", "EN 1090"],
    },
    OutsourceCategory.VERSPANING_5AS: {
        "typical_lead_time": "10-15 werkdagen",
        "min_order": "€200",
        "certifications": ["ISO 9001", "AS9100"],
    },
    OutsourceCategory.WARMTEBEHANDELING: {
        "typical_lead_time": "5-7 werkdagen",
        "min_order": "€50",
        "certifications": ["ISO 9001", "Nadcap"],
    },
    OutsourceCategory.OPPERVLAKTEBEHANDELING: {
        "typical_lead_time": "3-5 werkdagen",
        "min_order": "€25",
        "certifications": ["ISO 9001", "ISO 14001"],
    },
}


# =============================================================================
# OPPERVLAKTEBEHANDELING DATABASE
# =============================================================================

SURFACE_TREATMENTS = {
    # Bescherming / Corrosie
    "verzinken_elektrolytisch": {
        "name": "Elektrolytisch verzinken",
        "standard": "ISO 2081",
        "thickness": "5-25 μm",
        "suitable_for": ["steel_s235", "steel_s355", "steel_c45"],
        "cost_factor": 1.0,
        "lead_time_days": 3,
        "color_options": ["blank", "geel", "zwart", "blauw"],
    },
    "verzinken_thermisch": {
        "name": "Thermisch verzinken (dompelverzinken)",
        "standard": "ISO 1461",
        "thickness": "45-85 μm",
        "suitable_for": ["steel_s235", "steel_s355"],
        "cost_factor": 0.8,
        "lead_time_days": 5,
        "color_options": ["grijs"],
    },
    "anodiseren": {
        "name": "Anodiseren",
        "standard": "ISO 7599",
        "thickness": "10-25 μm",
        "suitable_for": ["alu_6061", "alu_6082", "alu_7075", "alu_5083"],
        "cost_factor": 1.2,
        "lead_time_days": 5,
        "color_options": ["naturel", "zwart", "rood", "blauw", "goud"],
    },
    "hardanodiseren": {
        "name": "Hardanodiseren",
        "standard": "ISO 10074",
        "thickness": "25-75 μm",
        "suitable_for": ["alu_6061", "alu_6082", "alu_7075"],
        "cost_factor": 2.0,
        "lead_time_days": 7,
        "color_options": ["grijs-zwart"],
        "hardness": "400-600 HV",
    },
    "poedercoaten": {
        "name": "Poedercoaten",
        "standard": "ISO 12944",
        "thickness": "60-120 μm",
        "suitable_for": ["steel_s235", "steel_s355", "alu_6061", "alu_6082"],
        "cost_factor": 1.0,
        "lead_time_days": 3,
        "color_options": ["RAL kleuren"],
    },
    "natlakken": {
        "name": "Natlakken (2K PU)",
        "standard": "ISO 12944",
        "thickness": "30-80 μm",
        "suitable_for": ["steel_s235", "steel_s355", "alu_6061"],
        "cost_factor": 1.3,
        "lead_time_days": 5,
        "color_options": ["RAL kleuren", "metallic"],
    },
    "passiveren_rvs": {
        "name": "Passiveren RVS",
        "standard": "ASTM A967",
        "thickness": "1-3 μm",
        "suitable_for": ["steel_304", "steel_316"],
        "cost_factor": 0.5,
        "lead_time_days": 2,
        "color_options": ["onveranderd"],
    },
    "nikkel_chemisch": {
        "name": "Chemisch vernikkelen",
        "standard": "ISO 4527",
        "thickness": "10-50 μm",
        "suitable_for": ["steel_s235", "steel_c45", "steel_42crmo4", "alu_6061"],
        "cost_factor": 3.0,
        "lead_time_days": 5,
        "hardness": "500-700 HV (na warmtebehandeling)",
    },
    "verchromen": {
        "name": "Hardverchromen",
        "standard": "ISO 6158",
        "thickness": "10-100 μm",
        "suitable_for": ["steel_c45", "steel_42crmo4"],
        "cost_factor": 4.0,
        "lead_time_days": 7,
        "hardness": "850-1050 HV",
    },
    "bruneren": {
        "name": "Bruneren (zwarten)",
        "standard": "DIN 50938",
        "thickness": "1-2 μm",
        "suitable_for": ["steel_s235", "steel_c45"],
        "cost_factor": 0.6,
        "lead_time_days": 2,
        "color_options": ["zwart"],
        "note": "Alleen decoratief, geen corrosiebescherming",
    },
}


# Warmtebehandelingen
HEAT_TREATMENTS = {
    "harden_en_ontlaten": {
        "name": "Harden en ontlaten",
        "standard": "ISO 683",
        "suitable_for": ["steel_c45", "steel_42crmo4"],
        "hardness_range": "45-60 HRC",
        "cost_factor": 1.5,
        "lead_time_days": 5,
    },
    "nitreren": {
        "name": "Gasnitreren",
        "standard": "ISO 10276",
        "suitable_for": ["steel_42crmo4", "steel_c45"],
        "hardness_range": "60-70 HRC (oppervlak)",
        "depth": "0.2-0.6 mm",
        "cost_factor": 2.5,
        "lead_time_days": 7,
    },
    "inductieharden": {
        "name": "Inductieharden",
        "standard": "ISO 3754",
        "suitable_for": ["steel_c45", "steel_42crmo4"],
        "hardness_range": "50-62 HRC",
        "depth": "1-4 mm",
        "cost_factor": 2.0,
        "lead_time_days": 5,
    },
    "spanningsarm_gloeien": {
        "name": "Spanningsarm gloeien",
        "standard": "ISO 683",
        "suitable_for": ["steel_s235", "steel_s355", "steel_c45", "alu_6061"],
        "cost_factor": 0.8,
        "lead_time_days": 3,
    },
}


# =============================================================================
# BEWERKINGSTIJD SCHATTING
# =============================================================================

def estimate_machining_time(
    volume_mm3: float,
    surface_area_mm2: float,
    hole_count: int,
    thread_count: int,
    complexity: str,
    process_type: str,
    material: str = "steel_s235"
) -> Dict[str, Any]:
    """
    Schat bewerkingstijd op basis van geometrie en complexiteit.

    Gebaseerd op VDI 3321 / ervaringswaarden Nederlandse verspaning.
    """
    # Volume naar cm³
    volume_cm3 = volume_mm3 / 1000

    # Materiaal factor (hardheid beïnvloedt snijsnelheid)
    material_factors = {
        "steel_s235": 1.0,
        "steel_s355": 1.1,
        "steel_304": 1.5,
        "steel_316": 1.6,
        "steel_c45": 1.2,
        "steel_42crmo4": 1.4,
        "alu_6061": 0.5,
        "alu_7075": 0.6,
        "messing": 0.6,
        "pom": 0.4,
    }
    mat_factor = material_factors.get(material, 1.0)

    # Complexiteit factor
    complexity_factors = {"low": 1.0, "medium": 1.5, "high": 2.5}
    comp_factor = complexity_factors.get(complexity, 1.0)

    # Bereken basis bewerkingstijd per proces
    if process_type == "cnc_draaien":
        # Verspaanvolume schatting: 70% van bounding box
        removal_rate = 15.0 / mat_factor  # cm³/min voor draaien
        base_time = (volume_cm3 * 0.3) / removal_rate  # 30% materiaal verwijderen

    elif process_type in ["cnc_frezen_3as", "cnc_frezen_5as"]:
        # Frezen: oppervlakte + volume gebaseerd
        removal_rate = 8.0 / mat_factor  # cm³/min voor frezen
        base_time = (volume_cm3 * 0.4) / removal_rate
        # Oppervlakte afwerking
        surface_time = (surface_area_mm2 / 10000) * 2.0 * mat_factor  # min per 100cm²
        base_time += surface_time

    elif process_type == "plaatwerk":
        # Plaatwerk: snijlengte + buigingen
        # Geschat op basis van oppervlakte
        cutting_time = (surface_area_mm2 / 10000) * 0.5  # min per 100cm²
        base_time = cutting_time

    else:
        base_time = volume_cm3 * 0.1 * mat_factor

    # Feature tijd toevoegen
    hole_time = hole_count * 0.5 * mat_factor  # 0.5 min per gat gemiddeld
    thread_time = thread_count * 1.0 * mat_factor  # 1 min per tap

    # Totale bewerkingstijd
    machining_time = (base_time + hole_time + thread_time) * comp_factor

    # Setup tijd
    if complexity == "high" or process_type == "cnc_frezen_5as":
        setup_time = HOURLY_RATES["setup_5as"]
    elif complexity == "medium":
        setup_time = HOURLY_RATES["setup_gemiddeld"]
    else:
        setup_time = HOURLY_RATES["setup_eenvoudig"]

    # Nabewerkingstijd (ontbramen, controleren)
    finishing_time = max(5.0, machining_time * 0.15)  # min 5 min, 15% van bewerking

    return {
        "machining_time_min": round(machining_time, 1),
        "setup_time_hours": setup_time,
        "finishing_time_min": round(finishing_time, 1),
        "total_time_hours": round((machining_time + finishing_time) / 60 + setup_time, 2),
        "factors": {
            "material": mat_factor,
            "complexity": comp_factor,
        },
    }


# =============================================================================
# KOSTPRIJSBEREKENING
# =============================================================================

def calculate_cost_estimate(
    volume_mm3: float,
    surface_area_mm2: float,
    mass_kg: float,
    hole_count: int,
    thread_count: int,
    complexity: str,
    process_type: str,
    material: str = "steel_s235",
    quantity: int = 1,
    surface_treatment: Optional[str] = None,
    hourly_rates_config: Optional[Dict[str, float]] = None,
    material_prices_config: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Bereken indicatieve kostprijs per onderdeel.

    Inclusief materiaal, bewerking, nabewerking en oppervlaktebehandeling.

    Args:
        hourly_rates_config: Optional dict with custom hourly rates (from config)
        material_prices_config: Optional dict with custom material prices (from config)
    """
    # Merge custom rates with defaults
    rates = {**HOURLY_RATES}
    if hourly_rates_config:
        rates.update(hourly_rates_config)

    # Merge custom material prices with defaults
    mat_prices = {k: v.copy() if isinstance(v, dict) else v for k, v in MATERIAL_PRICES.items()}
    if material_prices_config:
        for mat_key, price in material_prices_config.items():
            if mat_key in mat_prices:
                mat_prices[mat_key]["price_kg"] = price
            else:
                mat_prices[mat_key] = {"price_kg": price, "name": mat_key}

    # Materiaalkosten
    mat_info = mat_prices.get(material, mat_prices.get("steel_s235", {"price_kg": 1.20, "name": "Steel"}))
    # Materiaal opslag (ruw materiaal is groter dan eindproduct)
    raw_material_factor = 1.5 if "frezen" in process_type else 1.2
    material_cost = mass_kg * raw_material_factor * mat_info["price_kg"]

    # Bewerkingstijd en kosten
    time_est = estimate_machining_time(
        volume_mm3, surface_area_mm2, hole_count, thread_count,
        complexity, process_type, material
    )

    # Uurtarief selecteren
    rate_key = process_type
    if process_type == "cnc_draaien":
        if mass_kg < 1:
            rate_key = "cnc_draaien_klein"
        elif mass_kg < 10:
            rate_key = "cnc_draaien_middel"
        else:
            rate_key = "cnc_draaien_groot"

    hourly_rate = rates.get(rate_key, 60.0)
    machining_cost = time_est["total_time_hours"] * hourly_rate

    # Oppervlaktebehandeling
    treatment_cost = 0.0
    treatment_info = None
    if surface_treatment and surface_treatment in SURFACE_TREATMENTS:
        treatment_info = SURFACE_TREATMENTS[surface_treatment]
        # Kosten op basis van oppervlakte en massa
        base_treatment = (surface_area_mm2 / 10000) * 5.0  # €5 per 100cm²
        treatment_cost = base_treatment * treatment_info["cost_factor"]
        treatment_cost = max(15.0, treatment_cost)  # Minimum €15

    # Serie korting
    if quantity >= 100:
        series_discount = 0.70  # 30% korting
    elif quantity >= 50:
        series_discount = 0.80
    elif quantity >= 20:
        series_discount = 0.85
    elif quantity >= 10:
        series_discount = 0.90
    elif quantity >= 5:
        series_discount = 0.95
    else:
        series_discount = 1.0

    # Setup verdelen over serie
    setup_cost_per_piece = (time_est["setup_time_hours"] * hourly_rate) / quantity

    # Totale kostprijs per stuk
    cost_per_piece = (
        material_cost +
        (machining_cost - setup_cost_per_piece * quantity) / quantity * series_discount +
        setup_cost_per_piece +
        treatment_cost
    )

    return {
        "cost_per_piece": round(cost_per_piece, 2),
        "total_cost": round(cost_per_piece * quantity, 2),
        "breakdown": {
            "material": round(material_cost, 2),
            "machining": round(machining_cost * series_discount, 2),
            "setup_per_piece": round(setup_cost_per_piece, 2),
            "surface_treatment": round(treatment_cost, 2),
        },
        "time_estimate": time_est,
        "series_discount": f"{int((1 - series_discount) * 100)}%",
        "material_info": mat_info,
        "treatment_info": treatment_info,
        "hourly_rate": hourly_rate,
    }


# =============================================================================
# GEREEDSCHAPSLIJST GENEREREN
# =============================================================================

def generate_tool_list(
    holes: List[Dict],
    threads: List[Dict],
    chamfers_fillets: Dict,
    is_turned: bool,
    material: str = "steel_s235"
) -> List[Dict]:
    """
    Genereer gereedschapslijst op basis van features.
    """
    tool_list = []
    seen_tools = set()

    # Materiaal bepaalt gereedschaptype (HSS vs VHM)
    use_carbide = material in ["steel_304", "steel_316", "steel_42crmo4"]

    # Boren voor gaten
    for hole in holes:
        diameter = hole.get("diameter", 0)
        if diameter <= 0:
            continue

        # Standaard boor
        drill_key = f"drill_{diameter}"
        if drill_key not in seen_tools:
            if use_carbide:
                tool = TOOL_DATABASE["drill_vhm"](diameter)
            else:
                tool = TOOL_DATABASE["drill_hss"](diameter)

            tool_list.append({
                "tool_type": tool.tool_type.value,
                "designation": tool.designation,
                "diameter": diameter,
                "description": tool.description,
                "quantity_needed": 1,
                "estimated_cost": tool.typical_cost,
                "cutting_data": {
                    "speed_m_min": tool.cutting_speed,
                    "feed_mm_rev": tool.feed_per_tooth,
                },
            })
            seen_tools.add(drill_key)

    # Tappen voor schroefdraad
    for thread in threads:
        designation = thread.get("thread_designation", "")
        if not designation:
            continue

        tap_key = f"tap_{designation}"
        if tap_key not in seen_tools:
            # Parse M6x1.0 format
            parts = designation.replace("M", "").replace("x", " ").split()
            if len(parts) >= 1:
                try:
                    m_size = float(parts[0])
                    pitch = float(parts[1]) if len(parts) > 1 else m_size * 0.15  # Estimate

                    tool_list.append({
                        "tool_type": "tap",
                        "designation": f"{designation} tap",
                        "diameter": m_size,
                        "description": f"HSS machinetap {designation}",
                        "quantity_needed": 1,
                        "estimated_cost": 15.0 + m_size * 1.5,
                        "cutting_data": {
                            "speed_m_min": 12.0 if not use_carbide else 8.0,
                            "feed_mm_rev": pitch,
                        },
                        "tap_drill": thread.get("tap_drill"),
                    })
                    seen_tools.add(tap_key)
                except (ValueError, IndexError):
                    pass

    # Verzinkboren voor chamfers
    cf = chamfers_fillets or {}
    if cf.get("chamfer_count", 0) > 0:
        tool_list.append({
            "tool_type": "verzinkboor",
            "designation": "90° verzinkboor Ø20",
            "diameter": 20.0,
            "description": "HSS verzinkboor 90° voor afschuinen",
            "quantity_needed": 1,
            "estimated_cost": 25.0,
        })

    # Algemene frezen (indien niet draaien)
    if not is_turned:
        # Standaard frezenset
        for d in [6, 10, 16]:
            frees_key = f"frees_{d}"
            if frees_key not in seen_tools:
                if use_carbide:
                    tool = TOOL_DATABASE["endmill_vhm"](d)
                else:
                    tool = TOOL_DATABASE["endmill_hss"](d)

                tool_list.append({
                    "tool_type": tool.tool_type.value,
                    "designation": tool.designation,
                    "diameter": d,
                    "description": tool.description,
                    "quantity_needed": 1,
                    "estimated_cost": tool.typical_cost,
                    "cutting_data": {
                        "speed_m_min": tool.cutting_speed,
                        "feed_mm_tooth": tool.feed_per_tooth,
                    },
                })
                seen_tools.add(frees_key)

    return tool_list


# =============================================================================
# UITBESTEDING CLASSIFIER
# =============================================================================

def classify_outsourcing(
    classification: str,
    complexity: str,
    is_turned: bool,
    is_sheet_metal: bool,
    volume_mm3: float,
    surface_finish_ra: float = 3.2,
    has_5axis_features: bool = False,
    needs_heat_treatment: bool = False,
    needs_surface_treatment: bool = False
) -> Dict[str, Any]:
    """
    Classificeer naar welk type leverancier uitbesteed moet worden.
    """
    categories = []
    routing = []

    # Primaire bewerking
    if is_sheet_metal:
        categories.append(OutsourceCategory.PLAATWERK)
        routing.append({
            "step": 1,
            "category": OutsourceCategory.PLAATWERK.value,
            "description": "Lasersnijden + kanten",
            "info": OUTSOURCE_SUPPLIERS.get(OutsourceCategory.PLAATWERK, {}),
        })
    elif is_turned:
        categories.append(OutsourceCategory.CNC_DRAAIEN)
        routing.append({
            "step": 1,
            "category": OutsourceCategory.CNC_DRAAIEN.value,
            "description": "CNC draaien",
            "info": OUTSOURCE_SUPPLIERS.get(OutsourceCategory.CNC_DRAAIEN, {}),
        })
    elif has_5axis_features or complexity == "high":
        categories.append(OutsourceCategory.VERSPANING_5AS)
        routing.append({
            "step": 1,
            "category": OutsourceCategory.VERSPANING_5AS.value,
            "description": "5-assig CNC frezen",
            "info": OUTSOURCE_SUPPLIERS.get(OutsourceCategory.VERSPANING_5AS, {}),
        })
    else:
        categories.append(OutsourceCategory.CNC_FREZEN)
        routing.append({
            "step": 1,
            "category": OutsourceCategory.CNC_FREZEN.value,
            "description": "3/4-assig CNC frezen",
            "info": OUTSOURCE_SUPPLIERS.get(OutsourceCategory.CNC_FREZEN, {}),
        })

    # Slijpen indien hoge nauwkeurigheid nodig
    if surface_finish_ra < 0.8:
        categories.append(OutsourceCategory.SLIJPEN)
        routing.append({
            "step": len(routing) + 1,
            "category": OutsourceCategory.SLIJPEN.value,
            "description": f"Slijpen voor Ra {surface_finish_ra}",
            "info": OUTSOURCE_SUPPLIERS.get(OutsourceCategory.SLIJPEN, {}),
        })

    # Warmtebehandeling
    if needs_heat_treatment:
        categories.append(OutsourceCategory.WARMTEBEHANDELING)
        routing.append({
            "step": len(routing) + 1,
            "category": OutsourceCategory.WARMTEBEHANDELING.value,
            "description": "Harden/nitreren",
            "info": OUTSOURCE_SUPPLIERS.get(OutsourceCategory.WARMTEBEHANDELING, {}),
        })

    # Oppervlaktebehandeling
    if needs_surface_treatment:
        categories.append(OutsourceCategory.OPPERVLAKTEBEHANDELING)
        routing.append({
            "step": len(routing) + 1,
            "category": OutsourceCategory.OPPERVLAKTEBEHANDELING.value,
            "description": "Coating/behandeling",
            "info": OUTSOURCE_SUPPLIERS.get(OutsourceCategory.OPPERVLAKTEBEHANDELING, {}),
        })

    # Bereken totale doorlooptijd
    total_lead_time = sum(
        int(r["info"].get("typical_lead_time", "0").split("-")[0])
        for r in routing if r.get("info")
    )

    return {
        "primary_category": categories[0].value if categories else "intern",
        "all_categories": [c.value for c in categories],
        "routing": routing,
        "estimated_lead_time_days": total_lead_time,
        "recommendation": _get_outsource_recommendation(categories, complexity, volume_mm3),
    }


def _get_outsource_recommendation(
    categories: List[OutsourceCategory],
    complexity: str,
    volume_mm3: float
) -> str:
    """Genereer aanbeveling voor uitbesteding."""
    if not categories:
        return "Interne productie aanbevolen"

    if OutsourceCategory.VERSPANING_5AS in categories:
        return "Uitbesteden aan gespecialiseerde 5-assige leverancier (bijv. KMWE, NTS)"

    if complexity == "high":
        return "Uitbesteden aan ervaren leverancier met ISO 9001 certificering"

    if volume_mm3 > 1e6:  # Groot onderdeel
        return "Grotere verspaner met voldoende machinecapaciteit"

    return "Standaard uitbesteding mogelijk bij diverse leveranciers"


# =============================================================================
# OPPERVLAKTEBEHANDELING AANBEVELING
# =============================================================================

def recommend_surface_treatment(
    material: str,
    application: str = "general",
    corrosion_resistance: str = "normal",
    wear_resistance: bool = False,
    aesthetic: bool = False,
    color: Optional[str] = None
) -> List[Dict]:
    """
    Aanbevolen oppervlaktebehandelingen op basis van eisen.

    Args:
        material: Materiaalcode (bijv. "steel_s235", "alu_6061")
        application: "general", "outdoor", "food", "medical", "aerospace"
        corrosion_resistance: "minimal", "normal", "high", "extreme"
        wear_resistance: Slijtvastheid nodig
        aesthetic: Esthetisch uiterlijk belangrijk
        color: Gewenste kleur (optioneel)
    """
    recommendations = []

    # Filter behandelingen op materiaal
    suitable_treatments = []
    for key, treatment in SURFACE_TREATMENTS.items():
        if material in treatment.get("suitable_for", []):
            suitable_treatments.append((key, treatment))

    if not suitable_treatments:
        return [{"warning": f"Geen standaard behandelingen voor {material}"}]

    # Score berekenen per behandeling
    for key, treatment in suitable_treatments:
        score = 0
        notes = []

        # Corrosieweerstand
        if "verzinken" in key and corrosion_resistance in ["normal", "high"]:
            score += 3
            notes.append("Goede corrosiebescherming")
        if "thermisch" in key and corrosion_resistance == "high":
            score += 4
            notes.append("Uitstekende corrosiebescherming voor buiten")
        if "anodiseren" in key:
            score += 2 if corrosion_resistance != "minimal" else 0

        # Slijtvastheid
        if wear_resistance:
            if "hard" in key.lower():
                score += 5
                notes.append("Hoge slijtvastheid")
            if "verchromen" in key:
                score += 4
                notes.append("Zeer harde laag")
            if "nitreren" in key:
                score += 4
                notes.append("Oppervlakteharding")

        # Esthetiek / kleur
        if aesthetic:
            if "poedercoaten" in key or "anodiseren" in key:
                score += 3
                notes.append("Goede kleuropties")

        if color and color.lower() in [c.lower() for c in treatment.get("color_options", [])]:
            score += 2
            notes.append(f"Kleur {color} beschikbaar")

        # Speciale toepassingen
        if application == "food" and "passiveren" in key:
            score += 5
            notes.append("Geschikt voor voedselcontact")
        if application == "medical" and material in ["steel_304", "steel_316"]:
            if "passiveren" in key:
                score += 4

        # Kostenefficiëntie
        cost = treatment.get("cost_factor", 1.0)
        if cost < 1.0:
            score += 1
            notes.append("Kostenefficiënt")

        if score > 0:
            recommendations.append({
                "treatment": key,
                "name": treatment["name"],
                "standard": treatment.get("standard", ""),
                "thickness": treatment.get("thickness", ""),
                "score": score,
                "cost_factor": cost,
                "lead_time_days": treatment.get("lead_time_days", 5),
                "notes": notes,
                "color_options": treatment.get("color_options", []),
            })

    # Sorteer op score
    recommendations.sort(key=lambda x: x["score"], reverse=True)

    return recommendations[:5]  # Top 5


# =============================================================================
# INKOOP SPECIFICATIE GENEREREN
# =============================================================================

def generate_purchase_spec(
    part_id: str,
    material: str,
    mass_kg: float,
    dimensions: List[float],
    quantity: int = 1
) -> Dict:
    """
    Genereer materiaal inkoopspecificatie.
    """
    mat_info = MATERIAL_PRICES.get(material, {})

    # Bepaal ruw materiaal afmetingen (overmaat voor bewerking)
    overmaat = 5.0  # mm per zijde
    raw_dims = [d + overmaat * 2 for d in sorted(dimensions)]

    # Materiaal vorm bepalen
    if raw_dims[0] < raw_dims[1] * 0.1:
        form = "plaat"
        raw_format = f"{raw_dims[0]:.1f} x {raw_dims[1]:.0f} x {raw_dims[2]:.0f} mm"
    elif raw_dims[2] / raw_dims[1] > 3:
        form = "rondstaf" if raw_dims[0] / raw_dims[1] > 0.8 else "vierkantstaf"
        raw_format = f"Ø{max(raw_dims[0], raw_dims[1]):.0f} x {raw_dims[2]:.0f} mm"
    else:
        form = "blok"
        raw_format = f"{raw_dims[0]:.0f} x {raw_dims[1]:.0f} x {raw_dims[2]:.0f} mm"

    # Ruw gewicht (met overmaat)
    volume_raw = raw_dims[0] * raw_dims[1] * raw_dims[2]  # mm³
    density = 7.85 if "steel" in material else 2.70 if "alu" in material else 8.5
    raw_mass = (volume_raw / 1e9) * density * 1000  # kg

    # Materiaal certificaat
    cert_required = "EN 10204 3.1" if material in ["steel_304", "steel_316", "steel_42crmo4"] else "EN 10204 2.2"

    return {
        "part_id": part_id,
        "material": {
            "code": material,
            "name": mat_info.get("name", material),
            "standard": _get_material_standard(material),
        },
        "raw_material": {
            "form": form,
            "dimensions": raw_format,
            "mass_per_piece_kg": round(raw_mass, 2),
            "total_mass_kg": round(raw_mass * quantity, 2),
        },
        "quantity": quantity,
        "certification": cert_required,
        "estimated_cost": {
            "per_kg": mat_info.get("price_kg", 0),
            "per_piece": round(raw_mass * mat_info.get("price_kg", 0), 2),
            "total": round(raw_mass * quantity * mat_info.get("price_kg", 0), 2),
        },
        "notes": _get_material_notes(material),
    }


def _get_material_standard(material: str) -> str:
    """Haal materiaalstandaard op."""
    standards = {
        "steel_s235": "EN 10025-2",
        "steel_s355": "EN 10025-2",
        "steel_304": "EN 10088-2",
        "steel_316": "EN 10088-2",
        "steel_c45": "EN 10083-2",
        "steel_42crmo4": "EN 10083-3",
        "alu_6061": "EN 573-3 / EN 755-2",
        "alu_6082": "EN 573-3 / EN 755-2",
        "alu_7075": "EN 573-3",
    }
    return standards.get(material, "Op aanvraag")


def _get_material_notes(material: str) -> List[str]:
    """Materiaal specifieke opmerkingen."""
    notes = []
    if "304" in material or "316" in material:
        notes.append("Let op: RVS vereist speciale gereedschappen")
    if "7075" in material:
        notes.append("Luchtvaart legering - certificaat verplicht")
    if "42crmo4" in material:
        notes.append("Geleverd in gegloeid toestand (+A)")
    return notes


# =============================================================================
# EENVOUDIG KOSTENOVERZICHT PER ONDERDEEL
# =============================================================================

def calculate_part_cost_breakdown(
    part_data: Dict,
    material: str = "steel_s235",
    quantity: int = 1,
    hourly_rates_config: Optional[Dict[str, float]] = None,
    material_prices_config: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Bereken kosten per onderdeel uitgesplitst naar bewerkingstype.

    Retourneert kosten voor: Snijden, Ink./st, Zagen, Zetten, Verspanen,
    Logistiek, Lassen, Boren, Assembleren

    Args:
        part_data: Dict met part informatie (volume, holes, threads, dims, etc.)
        material: Materiaalcode
        quantity: Aantal stuks
        hourly_rates_config: Custom uurtarieven
        material_prices_config: Custom materiaalprijzen

    Returns:
        Dict met kosten per bewerkingstype
    """
    # Merge rates
    rates = {**HOURLY_RATES}
    if hourly_rates_config:
        rates.update(hourly_rates_config)

    # Merge material prices
    mat_prices = {k: v.copy() if isinstance(v, dict) else v for k, v in MATERIAL_PRICES.items()}
    if material_prices_config:
        for mat_key, price in material_prices_config.items():
            if mat_key in mat_prices:
                mat_prices[mat_key]["price_kg"] = price
            else:
                mat_prices[mat_key] = {"price_kg": price, "name": mat_key}

    # Extract part properties
    volume = part_data.get('volume', 0)
    dims = part_data.get('dimensions', [0, 0, 0])
    holes = part_data.get('holes', [])
    threads = part_data.get('threads', [])
    is_sheet_metal = part_data.get('sheet_metal', {}).get('is_sheet_metal', False)
    bend_count = part_data.get('sheet_metal', {}).get('bend_count', 0)
    classification = part_data.get('classification', 'unknown')

    # Calculate mass
    density = 7850 if "steel" in material else 2700 if "alu" in material else 7850
    mass_kg = (volume / 1e9) * density

    # Material price
    mat_info = mat_prices.get(material, {"price_kg": 1.50})
    mat_price_kg = mat_info["price_kg"] if isinstance(mat_info, dict) else mat_info

    # Initialize cost breakdown
    costs = {
        "snijden": 0.0,
        "ink_per_stuk": 0.0,
        "zagen": 0.0,
        "zetten": 0.0,
        "verspanen": 0.0,
        "logistiek": 0.0,
        "lassen": 0.0,
        "boren": 0.0,
        "assembleren": 0.0,
    }

    # === INKOOP PER STUK (materiaalkosten) ===
    raw_factor = 1.3  # Opslag voor ruw materiaal
    costs["ink_per_stuk"] = mass_kg * raw_factor * mat_price_kg

    # === SNIJDEN (laser/plasma voor plaatwerk) ===
    if is_sheet_metal:
        # Snijden: gebaseerd op omtrek
        perimeter = 2 * (dims[0] + dims[1]) if len(dims) >= 2 else 0
        snij_lengte_m = perimeter / 1000
        snij_snelheid_m_min = 2.0  # Gemiddelde snijsnelheid
        snij_tijd_uur = (snij_lengte_m / snij_snelheid_m_min) / 60
        costs["snijden"] = snij_tijd_uur * rates.get("laser_snijden", 70.0)

    # === ZAGEN (voor blokken/staven) ===
    if not is_sheet_metal and classification in ['block', 'shaft', 'other']:
        # Zagen: ~2 min per zaagsnede
        zaag_tijd_uur = 2 / 60
        costs["zagen"] = zaag_tijd_uur * rates.get("plasma_snijden", 55.0)

    # === ZETTEN (kantbank voor plaatwerk) ===
    if bend_count > 0:
        # ~1 min per zetting
        zet_tijd_uur = (bend_count * 1) / 60
        costs["zetten"] = zet_tijd_uur * rates.get("kanten", 45.0)

    # === VERSPANEN (CNC frezen/draaien) ===
    if classification in ['shaft', 'turned_part']:
        # Draaien
        draai_tijd = (volume / 1e6) * 0.5  # Uren per cm³ (indicatief)
        draai_tijd = max(0.1, min(draai_tijd, 2.0))  # Min 6 min, max 2 uur
        costs["verspanen"] = draai_tijd * rates.get("cnc_draaien_middel", 65.0)
    elif not is_sheet_metal:
        # Frezen
        frees_tijd = (volume / 1e6) * 0.3  # Uren per cm³
        frees_tijd = max(0.1, min(frees_tijd, 3.0))
        costs["verspanen"] = frees_tijd * rates.get("cnc_frezen_3as", 60.0)

    # === BOREN ===
    if holes:
        hole_count = len(holes) if isinstance(holes, list) else holes
        # ~0.5 min per gat
        boor_tijd_uur = (hole_count * 0.5) / 60
        costs["boren"] = boor_tijd_uur * rates.get("cnc_frezen_3as", 60.0)

    # === LASSEN ===
    # Alleen als onderdeel gelast moet worden (check op basis van classificatie)
    if classification in ['weldment', 'frame', 'bracket']:
        # Schat laslengte op basis van omtrek
        las_lengte_mm = sum(dims[:2]) * 2 if len(dims) >= 2 else 100
        las_snelheid_mm_min = 150  # Gemiddelde lassnelheid
        las_tijd_uur = (las_lengte_mm / las_snelheid_mm_min) / 60
        costs["lassen"] = las_tijd_uur * rates.get("lassen_mig", 50.0)

    # === LOGISTIEK ===
    # Vaste opslag per onderdeel
    costs["logistiek"] = 2.0  # €2 per onderdeel

    # === ASSEMBLEREN ===
    # Alleen relevant voor samenstellingen
    if classification == 'assembly':
        costs["assembleren"] = 5.0  # Basis €5

    # Round all values
    for key in costs:
        costs[key] = round(costs[key], 2)

    return {
        "part_id": part_data.get('id', 'unknown'),
        "part_name": part_data.get('name', f"Part {part_data.get('id', '')}"),
        "article_number": part_data.get('article_number', ''),
        "classification": classification,
        "material": material,
        "quantity": quantity,
        "mass_kg": round(mass_kg, 3),
        "costs": costs,
        "total_per_piece": round(sum(costs.values()), 2),
        "total_for_quantity": round(sum(costs.values()) * quantity, 2),
    }


def generate_simple_cost_table(
    parts: List[Dict],
    material: str = "steel_s235",
    quantity: int = 1,
    hourly_rates_config: Optional[Dict[str, float]] = None,
    material_prices_config: Optional[Dict[str, float]] = None,
    enabled_columns: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Genereer eenvoudige kostentabel voor alle onderdelen.

    Formaat zoals screenshot:
    Aantal | Artikel | Soort | Materiaal | Snijden | Ink./st | Zagen | Zetten | ...

    Args:
        parts: Lijst met part data
        material: Default materiaal
        quantity: Aantal per part
        hourly_rates_config: Custom uurtarieven
        material_prices_config: Custom materiaalprijzen
        enabled_columns: Welke kostenkolommen te tonen

    Returns:
        Dict met tabel data en totalen
    """
    if enabled_columns is None:
        enabled_columns = [
            "snijden", "ink_per_stuk", "zagen", "zetten",
            "verspanen", "logistiek", "lassen", "boren", "assembleren"
        ]

    # Column headers (Dutch)
    column_names = {
        "snijden": "Snijden",
        "ink_per_stuk": "Ink./st",
        "zagen": "Zagen",
        "zetten": "Zetten",
        "verspanen": "Verspanen",
        "logistiek": "Logistiek",
        "lassen": "Lassen",
        "boren": "Boren",
        "assembleren": "Assembl.",
    }

    # Calculate costs for each part
    rows = []
    totals = {col: 0.0 for col in enabled_columns}
    grand_total = 0.0

    for part in parts:
        part_qty = part.get('count', quantity)
        part_material = part.get('material', material)

        breakdown = calculate_part_cost_breakdown(
            part,
            material=part_material,
            quantity=part_qty,
            hourly_rates_config=hourly_rates_config,
            material_prices_config=material_prices_config
        )

        row = {
            "aantal": part_qty,
            "artikel": breakdown.get('article_number') or breakdown.get('part_id', ''),
            "soort": breakdown.get('classification', ''),
            "materiaal": part_material,
        }

        # Add enabled cost columns
        for col in enabled_columns:
            cost_val = breakdown['costs'].get(col, 0.0)
            row[col] = cost_val
            totals[col] += cost_val * part_qty

        row["totaal"] = breakdown['total_per_piece']
        grand_total += breakdown['total_for_quantity']

        rows.append(row)

    # Build header
    headers = ["Aantal", "Artikel:", "Soort:", "Materiaal"]
    headers.extend([column_names.get(col, col) for col in enabled_columns])
    headers.append("Totaal")

    return {
        "headers": headers,
        "rows": rows,
        "totals": totals,
        "grand_total": round(grand_total, 2),
        "enabled_columns": enabled_columns,
        "column_names": column_names,
    }


# =============================================================================
# PLAATWERK PRODUCTIE INFO TABEL
# =============================================================================

def generate_production_info_table(
    parts: List[Dict],
    calc_id_prefix: str = "",
    material: str = "steel_s235"
) -> Dict[str, Any]:
    """
    Genereer productie info tabel voor plaatwerk onderdelen.

    Kolommen zoals in screenshot:
    CalcID | ArtikelNr | Aantal | Vorm | Lengte | Breedte | Dikte | Hoogte |
    Snijgaten | DiaSnijgat | ZetAantal | Intalegtemmen

    Args:
        parts: Lijst met part data (detailed_parts)
        calc_id_prefix: Prefix voor CalcID
        material: Default materiaal

    Returns:
        Dict met headers en rows
    """
    rows = []

    for idx, part in enumerate(parts, start=1):
        part_id = part.get('id', f'PART-{idx:03d}')
        artikel_nr = part.get('article_number', '') or part.get('name', '') or part_id

        # Get dimensions
        dims = part.get('dimensions', [0, 0, 0])
        if len(dims) < 3:
            dims = dims + [0] * (3 - len(dims))

        # Sort dimensions for L x B x H (largest to smallest for L, B)
        sorted_dims = sorted(dims, reverse=True)
        lengte = sorted_dims[0] if len(sorted_dims) > 0 else 0
        breedte = sorted_dims[1] if len(sorted_dims) > 1 else 0
        hoogte = sorted_dims[2] if len(sorted_dims) > 2 else 0

        # Sheet metal info
        sheet_metal = part.get('sheet_metal', {})
        is_sheet_metal = sheet_metal.get('is_sheet_metal', False)
        dikte = sheet_metal.get('thickness', 0) or 0
        zet_aantal = sheet_metal.get('bend_count', 0) or 0
        tegenzet_aantal = sheet_metal.get('counter_bend_count', 0) or 0

        # If not sheet metal, derive dikte from smallest dimension
        if not is_sheet_metal or dikte == 0:
            dikte = hoogte  # Smallest dimension as thickness

        # Determine form (Vorm)
        classification = part.get('classification', 'unknown')
        if is_sheet_metal:
            vorm = 'plaat'
        elif classification in ['shaft', 'turned_part', 'Shaft/Bar']:
            vorm = 'rond'
        elif classification in ['block', 'Block/Housing']:
            vorm = 'blok'
        elif classification in ['Fastener (Bolt/Screw/Pin)']:
            vorm = 'bout'
        elif classification in ['Washer/Spacer']:
            vorm = 'ring'
        else:
            vorm = 'plaat'  # Default to plaat

        # Holes info
        holes = part.get('holes', [])
        if isinstance(holes, list):
            snijgaten = len(holes)
            # Get most common diameter or largest
            if holes:
                diameters = []
                for h in holes:
                    if isinstance(h, dict):
                        diameters.append(h.get('diameter', 0))
                    elif isinstance(h, (int, float)):
                        diameters.append(h)
                dia_snijgat = max(diameters) if diameters else 0
            else:
                dia_snijgat = 0
        else:
            snijgaten = 0
            dia_snijgat = 0

        # Intalegtemmen (?)  - assuming this relates to positioning features or tabs
        # Based on context, likely related to nesting/positioning markers
        intalegtemmen = 0  # Default, can be derived from features if available

        # Quantity (from part count)
        aantal = part.get('count', 1)

        # Build CalcID
        calc_id = f"{calc_id_prefix}{idx:06d}" if calc_id_prefix else f"{idx:06d}"

        row = {
            "calc_id": calc_id,
            "artikel_nr": artikel_nr[:30],  # Truncate if too long
            "aantal": aantal,
            "vorm": vorm,
            "lengte": round(lengte, 1),
            "breedte": round(breedte, 1),
            "dikte": round(dikte, 1),
            "hoogte": round(hoogte, 1),
            "snijgaten": snijgaten,
            "dia_snijgat": round(dia_snijgat, 1),
            "zet_aantal": zet_aantal,
            "intalegtemmen": intalegtemmen,
        }
        rows.append(row)

    headers = [
        "CalcID", "ArtikelNr", "Aantal", "Vorm",
        "Lengte", "Breedte", "Dikte", "Hoogte",
        "Snijgaten", "DiaSnijgat", "ZetAantal", "Intalegtemmen"
    ]

    return {
        "headers": headers,
        "rows": rows,
        "total_parts": len(rows),
        "total_quantity": sum(r['aantal'] for r in rows),
    }
