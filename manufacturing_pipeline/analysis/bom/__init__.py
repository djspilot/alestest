"""Internal BOM helpers extracted from legacy analysis modules."""

from manufacturing_pipeline.analysis.bom.assembly_analysis import *  # noqa: F401,F403
from manufacturing_pipeline.analysis.bom import assembly_analysis as _assembly_analysis

_get_solid_surface_area = _assembly_analysis._get_solid_surface_area
_is_plate_by_face_analysis = _assembly_analysis._is_plate_by_face_analysis
