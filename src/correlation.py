from .models import MatchedFeature, ValidationStatus, HoleFeature

def correlate_hole_dimension(step_hole: HoleFeature, pdf_dimensions: list) -> MatchedFeature:
    """Match STEP hole geometry to PDF dimension annotation."""
    step_d = step_hole.diameter
    
    # Find matching diameter annotation
    for pdf_dim in pdf_dimensions:
        if pdf_dim.get('type') == 'diameter':
            pdf_d = pdf_dim['nominal']
            if abs(step_d - pdf_d) < 0.1:  # Within 0.1mm
                return MatchedFeature(
                    step_value=step_d,
                    pdf_value=pdf_d,
                    tolerance_upper=pdf_dim.get('upper_dev', 0),
                    tolerance_lower=pdf_dim.get('lower_dev', 0),
                    confidence=1.0 - abs(step_d - pdf_d) / step_d,
                    status=ValidationStatus.VALID
                )
    return None  # No match found
