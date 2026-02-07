from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

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
