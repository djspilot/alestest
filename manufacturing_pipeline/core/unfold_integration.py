"""
FreeCAD SheetMetal unfold integration and orchestration.

This module provides interface for unfolding sheet metal parts using FreeCAD.
- run_unfold_to_step: Main unfold orchestration with STEP export
- run_theoretical_unfold: Fallback unfold using bend geometry
- Thickness extraction from unfold results

Note: Main unfold logic (with embedded FreeCAD script) remains in utils.py
due to complexity. Future refactoring can extract script to templates/files.
"""

from typing import Any, Dict, Optional


# =============================================================================
# Unfold Integration Interface
# =============================================================================

def calculate_unfold_statistics(unfold_result: Optional[Dict]) -> Dict[str, Any]:
    """Extract useful statistics from unfold result.
    
    Returns: dict with normalized unfold metrics
    """
    if not unfold_result or not unfold_result.get('success'):
        return {
            'success': False,
            'flat_length': None,
            'flat_width': None,
            'fold_lines': 0,
            'thickness': None,
        }
    
    return {
        'success': True,
        'flat_length': unfold_result.get('flat_length', 0),
        'flat_width': unfold_result.get('flat_width', 0),
        'fold_lines': unfold_result.get('fold_lines', 0),
        'thickness': unfold_result.get('thickness', None),
        'flat_step_path': unfold_result.get('flat_step_path'),
        'error': unfold_result.get('error'),
    }


def merge_unfold_thickness_with_analysis(
    unfold_thickness: Optional[float],
    current_thickness: float,
    max_valid_thickness: float = 25.0
) -> Optional[float]:
    """Determine if unfold thickness should override current analysis thickness.
    
    Unfold is authoritative for thickness, but sanity-check against max valid.
    
    Returns: merged thickness or None if unfold value should not be used
    """
    if unfold_thickness is None or unfold_thickness <= 0:
        return None
    
    # Ignore if seems too large (likely assembly or measurement error)
    if unfold_thickness > max_valid_thickness:
        return None
    
    # Use unfold if current is 0 or significantly different
    if current_thickness == 0 or abs(current_thickness - unfold_thickness) > 0.1:
        return unfold_thickness
    
    return None


def should_attempt_unfold(part_category: str, 
                         no_unfold_flag: bool,
                         disabled_stages: set) -> bool:
    """Determine if unfold should be attempted based on classification and flags.
    
    Returns: bool indicating whether unfold should run
    """
    is_bent_sheet = part_category == "GEBOGEN PLAATWERK"
    is_enabled = not no_unfold_flag
    is_not_disabled = "unfold" not in disabled_stages
    
    return is_bent_sheet and is_enabled and is_not_disabled


# =============================================================================
# Thickness Detection Helpers
# =============================================================================

def validate_unfold_dimensions(flat_length: Optional[float],
                              flat_width: Optional[float],
                              max_dimension: float = 10000.0) -> bool:
    """Sanity-check unfold dimensions.
    
    Returns: True if dimensions are reasonable
    """
    if flat_length is None or flat_width is None:
        return False
    
    if flat_length <= 0 or flat_width <= 0:
        return False
    
    if flat_length > max_dimension or flat_width > max_dimension:
        return False
    
    return True


# =============================================================================
# Result Payload Builders
# =============================================================================

def build_unfold_event_payload(unfold_result: Optional[Dict]) -> Dict[str, Any]:
    """Build event payload for timeline emission.
    
    Standardizes unfold result for viewer/timeline integration.
    """
    success = bool(unfold_result and unfold_result.get("success"))
    
    return {
        "success": success,
        "flat_length": unfold_result.get("flat_length") if unfold_result else None,
        "flat_width": unfold_result.get("flat_width") if unfold_result else None,
        "fold_lines": unfold_result.get("fold_lines") if unfold_result else 0,
        "fold_details": unfold_result.get("fold_details", []) if unfold_result else [],
        "bends_logical": unfold_result.get("bends_logical", []) if unfold_result else [],
        "error": unfold_result.get("error") if unfold_result else None,
    }


__all__ = [
    "calculate_unfold_statistics",
    "merge_unfold_thickness_with_analysis",
    "should_attempt_unfold",
    "validate_unfold_dimensions",
    "build_unfold_event_payload",
]
