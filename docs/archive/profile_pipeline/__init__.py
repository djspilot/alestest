"""
STEP Profile Classification Pipeline.

Headless, configurable module for extracting and classifying
steel profile cross-sections from STEP files.

Usage:
    from profile_pipeline import classify_step_file, PipelineConfig

    results = classify_step_file("model.stp")
    results = classify_step_file("model.stp", config=PipelineConfig(num_sections=3))
"""

from .config import PipelineConfig
from .pipeline import classify_step_file, classify_step_solids
from .result import SolidResult, SectionResult, ClassificationResult

__all__ = [
    "PipelineConfig",
    "classify_step_file",
    "classify_step_solids",
    "SolidResult",
    "SectionResult",
    "ClassificationResult",
]
