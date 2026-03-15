from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

class RouteCategory(Enum):
    """Pre-routing classificatie: bepaalt welk pad de pipeline volgt."""
    PLAAT = "plaat"        # Vlakke plaat / plaatwerk (incl. gebogen plaat)
    PROFIEL = "profiel"    # Stalen profiel (I/U/L/T/koker)
    ROND = "rond"          # Rond staal / buis / draaistuk
    OVERIG = "overig"      # Niet geclassificeerd

class ValidationStatus(Enum):
    VALID = "valid"
    WARNING = "warning"        # Minor discrepancy
    ERROR = "error"            # Major conflict
    MANUAL_REQUIRED = "manual"

@dataclass
class HoleFeature:
    diameter: float
    depth: float
    position: Tuple[float, float, float]
    axis: Tuple[float, float, float]
    type: str = "unknown" # through, blind, etc.

@dataclass
class MatchedFeature:
    step_value: float
    pdf_value: float
    tolerance_upper: float
    tolerance_lower: float
    confidence: float
    status: ValidationStatus
