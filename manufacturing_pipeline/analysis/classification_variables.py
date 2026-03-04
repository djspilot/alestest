"""
Centralized classification thresholds and score-model settings.

This module is intentionally simple and dependency-free so all classification
logic can import the same source of truth.

DOCUMENTATION:
- Complete decision tree: docs/CLASSIFICATION_DECISION_TREE.md
- Architecture overview: docs/CLASSIFICATION_ARCHITECTURE.md
- Classification schema: docs/CLASSIFICATION_SCHEMA.md

USAGE:
    from manufacturing_pipeline.analysis.classification_variables import (
        PLATE_FACE_TOP2_THRESHOLD_PCT,
        STANDARD_TUBE_CYLINDRICAL_MIN_PCT,
        ...
    )

TUNING:
    1. Edit values below
    2. Test: python validate_classification_only.py
    3. Commit: git add -A && git commit -m "Tune: adjusted thresholds"

VERSION: 2.1 (Standard Profile Detection - 2 maart 2026)
"""

# =============================================================================
# PLATE DETECTION
# =============================================================================
# Top2 faces analysis (primary plate detection method)
PLATE_FACE_TOP2_THRESHOLD_PCT = 50.0  # >=50% surface area in top 2 faces → plate

# Thin plate bbox fallback (when face analysis inconclusive)
PLATE_THICK_MAX_MM = 25.0              # <25mm thickness
PLATE_THICKNESS_RATIO_MAX = 0.15       # smallest/middle < 0.15 (thin)
PLATE_ASPECT_RATIO_MIN = 5.0           # longest/middle > 5.0 (elongated)

# =============================================================================
# PROFILE DETECTION (Solid beams, bars)
# =============================================================================
PROFILE_SMALLEST_MIN_MM = 5.0          # >=5mm (not a thin sheet)
PROFILE_LENGTH_RATIO_MIN = 5.0         # longest/smallest >= 5.0 (elongated)
PROFILE_CROSS_RATIO_MIN = 0.5          # Rectangular cross-section
PROFILE_CROSS_RATIO_MAX = 2.0          #   0.5 <= smallest/middle <= 2.0
PROFILE_VOLUME_RATIO_STRONG_MIN = 0.5  # >0.5 volume fill → solid profile (strong)
PROFILE_VOLUME_RATIO_WEAK_MIN = 0.15   # 0.15-0.5 → ambiguous (use SA/V tiebreaker)
PROFILE_SA_V_RATIO_MAX = 1.2           # Surface/volume < 1.2 cm⁻¹ → solid (tiebreaker)

# =============================================================================
# SCORE MODEL (Feature-flagged via ALES_CLASSIFICATION_MODE=score)
# =============================================================================
SCORE_PLATE_TOP2_HIGH_PCT = 70.0
SCORE_PLATE_TOP2_MIN_PCT = 50.0
SCORE_PLATE_SUPPORT_TOP2_PCT = 45.0
SCORE_PLATE_SUPPORT_THICKNESS_RATIO_MAX = 0.35
SCORE_PLATE_SUPPORT_ASPECT_MIN = 2.0

SCORE_PROFILE_PRIMARY_POINTS = 2.0
SCORE_PLATE_PRIMARY_POINTS = 2.0
SCORE_AMBIGUOUS_MARGIN_MIN = 1.0

# =============================================================================
# STANDARD PROFILE DETECTION (v2.1 - Geometry-based fallback)
# =============================================================================
# These thresholds detect standard catalog items (DIN/EN/ISO) when STEP name
# parsing fails, using geometry signatures instead of metadata.

# Hollow tube detection (round/rectangular pipes, fittings)
STANDARD_TUBE_CYLINDRICAL_MIN_PCT = 60.0  # >=60% cylindrical faces (round tube)
STANDARD_TUBE_VOLUME_RATIO_MAX = 0.7      # <0.7 volume_ratio (hollow)
STANDARD_TUBE_ASPECT_MIN = 0.5            # Aspect L/D >=0.5 (not compressed)

# Variable thickness detection (UNP, I-beams, L-profiles)
STANDARD_PROFILE_VARIABLE_THICKNESS = True       # Enable check
STANDARD_PROFILE_ELONGATED_LENGTH_RATIO_MIN = 5.0  # L/smallest >= 5 (elongated)
STANDARD_PROFILE_FACE_AREA_TOLERANCE = 0.20      # Top2 faces differ >20% → variable

# =============================================================================
# BENT SHEET DETECTION (v2.1 - Formed/Folded Sheet Metal)
# =============================================================================
# Detect sheet metal that has been bent/formed (U-profiles, channels, trays)
# These should be classified as PLAAT even though they don't have high top2%

# Thickness constraint - bent sheets must be thin (like normal sheets)
# Note: For U-profiles, "smallest" dimension includes the hollow opening,
# so this is more generous (allows profiles with larger cross-sections)
BENT_SHEET_THICKNESS_MAX_MM = 100.0       # Relaxed: allows hollow sections with opening

# Edge count - bent sheets have many edges due to bends/folds  
BENT_SHEET_MIN_EDGE_COUNT = 8             # >=8 edges indicates folded geometry
                                          # Flat plate: ~4 edges
                                          # U-profile: ~12-16 edges
                                          # Channel: ~8-12 edges

# Volume ratio - bent sheets should be mostly air (not solid mass)
BENT_SHEET_VOLUME_RATIO_MIN = 0.10        # Lowered to 0.10 for hollow profiles
BENT_SHEET_VOLUME_RATIO_MAX = 0.50        # <0.50 (not solid profile)

# Top2 faces should NOT be too high (to distinguish from completely flat plates)
BENT_SHEET_TOP2_FACES_MAX_PCT = 60.0      # <60% (more distributed than flat plate)

# Aspect ratio - bent sheets are typically elongated
BENT_SHEET_ASPECT_RATIO_MIN = 2.0         # longest/smallest >= 2.0 (elongated)
