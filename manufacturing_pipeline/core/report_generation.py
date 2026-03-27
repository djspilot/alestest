"""
Report generation orchestration and analysis summary builders.

This module provides interfaces for:
- PDF report generation (compact and simple formats)
- AAG (Attributed Adjacency Graph) analysis reporting
- Result summaries and export formatting

Main PDF generation logic remains in utils.py due to reportlab
integration complexity. Future refactoring can extract templates.
"""

from typing import Any, Dict, Optional


# =============================================================================
# Report Type Constants
# =============================================================================

REPORT_FORMAT_SIMPLE = "simple"
REPORT_FORMAT_COMPACT = "compact"
REPORT_FORMAT_EXCEL = "excel"
REPORT_FORMAT_XML = "xml"


# =============================================================================
# Summary Builders
# =============================================================================

def build_part_summary(analysis: Any, 
                       total_holes: int,
                       unfold_result: Optional[Dict] = None) -> Dict[str, Any]:
    """Build comprehensive part analysis summary.
    
    Aggregates classification, geometry, holes, and unfold results
    into a single summary dict for reporting.
    """
    return {
        "part_category": getattr(analysis, "part_category", "UNKNOWN"),
        "part_type": getattr(getattr(analysis, "part_type", None), "value", None),
        "classification_source": getattr(analysis, "classification_source", "UNKNOWN"),
        "geometry": {
            "volume": round(float(getattr(analysis, "volume", 0) or 0), 6),
            "surface_area": round(float(getattr(analysis, "surface_area", 0) or 0), 6),
            "thickness": round(float(getattr(analysis, "thickness", 0) or 0), 3),
            "dimensions": {
                "length": round(float(getattr(analysis, "length", 0) or 0), 3),
                "width": round(float(getattr(analysis, "width", 0) or 0), 3),
                "height": round(float(getattr(analysis, "height", 0) or 0), 3),
            },
        },
        "holes": {
            "total": total_holes,
            "cylindrical": getattr(analysis, "hole_count_cylindrical", 0),
            "shaped": total_holes - getattr(analysis, "hole_count_cylindrical", 0),
        },
        "bends": {
            "total": getattr(analysis, "bend_count", 0),
            "erp_count": getattr(analysis, "bend_count_erp", 0),
        },
        "unfold": calculate_unfold_summary(unfold_result),
    }


def calculate_unfold_summary(unfold_result: Optional[Dict]) -> Dict[str, Any]:
    """Extract unfold summary from unfold result."""
    if not unfold_result or not unfold_result.get('success'):
        return {
            "success": False,
            "status": "FAILED" if unfold_result else "NOT_ATTEMPTED",
            "error": unfold_result.get('error') if unfold_result else None,
        }
    
    return {
        "success": True,
        "status": "SUCCESS",
        "flat_dimensions": {
            "length": unfold_result.get('flat_length', 0),
            "width": unfold_result.get('flat_width', 0),
        },
        "fold_lines": unfold_result.get('fold_lines', 0),
        "thickness_detected": unfold_result.get('thickness'),
    }


def build_hole_report(holes_list: list,
                      holes_debug: Optional[list] = None) -> Dict[str, Any]:
    """Build detailed hole detection report."""
    accepted = [h for h in (holes_list or [])]
    rejected = [h for h in (holes_debug or []) if h.get('status') == 'rejected']
    
    return {
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "total_checked": len(accepted) + len(rejected),
        "acceptance_rate": len(accepted) / max(1, len(accepted) + len(rejected)),
    }


def build_classification_report(analysis: Any) -> Dict[str, Any]:
    """Build classification decision report."""
    return {
        "source": getattr(analysis, "classification_source", "UNKNOWN"),
        "category": getattr(analysis, "part_category", "UNKNOWN"),
        "type": getattr(getattr(analysis, "part_type", None), "value", None),
        "confidence": getattr(analysis, "classification_confidence", None),
        "reasoning_count": len(getattr(analysis, "reasoning", [])),
    }


# =============================================================================
# Export Format Builders
# =============================================================================

def build_csv_export(summary: Dict[str, Any]) -> str:
    """Build CSV format export of analysis summary.
    
    Returns: CSV content as string
    """
    lines = [
        "Parameter,Value",
        f"Part Category,{summary.get('part_category', 'N/A')}",
        f"Part Type,{summary.get('part_type', 'N/A')}",
        f"Total Holes,{summary.get('holes', {}).get('total', 0)}",
        f"Total Bends,{summary.get('bends', {}).get('total', 0)}",
        f"Thickness (mm),{summary.get('geometry', {}).get('thickness', 0)}",
        f"Volume (mm³),{summary.get('geometry', {}).get('volume', 0)}",
        f"Unfold Success,{summary.get('unfold', {}).get('success', False)}",
    ]
    return "\n".join(lines)


def build_json_export(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Build JSON-serializable export of analysis summary."""
    return {**summary}


# =============================================================================
# Report Quality Metrics
# =============================================================================

def calculate_report_completeness(analysis: Any) -> float:
    """Calculate report completeness score (0-1).
    
    Indicates what percentage of expected analysis fields are populated.
    """
    expected_fields = [
        "part_category",
        "part_type",
        "thickness",
        "volume",
        "surface_area",
        "length",
        "width",
        "height",
        "hole_count_cylindrical",
        "bend_count",
        "bend_count_erp",
    ]
    
    available = sum(1 for field in expected_fields 
                   if getattr(analysis, field, None) is not None)
    
    return available / len(expected_fields) if expected_fields else 0.0


__all__ = [
    "REPORT_FORMAT_SIMPLE",
    "REPORT_FORMAT_COMPACT",
    "REPORT_FORMAT_EXCEL",
    "REPORT_FORMAT_XML",
    "build_part_summary",
    "calculate_unfold_summary",
    "build_hole_report",
    "build_classification_report",
    "build_csv_export",
    "build_json_export",
    "calculate_report_completeness",
]
