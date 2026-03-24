"""Pipeline configuration with sensible defaults."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PipelineConfig:
    """All tuneable parameters for the classification pipeline.

    Attributes:
        num_sections: Number of cross-section planes along the extrusion axis.
        section_range: (start, end) fractions along the axis to place sections.
            E.g. (0.15, 0.85) avoids the very ends where geometry may differ.
        template_accept_threshold: Maximum template-match distance to accept
            a classification. Lower = stricter.
        min_valid_sections: Minimum number of non-empty sections required
            before classification is attempted.
        cluster_stability_ratio: Minimum fraction of sections in the dominant
            cluster to consider the profile "stable".
        max_vertices_export: When exporting 3D vertices, subsample to this count.
        include_vertices: Whether to include 3D vertex coordinates in output.
        include_polygon_coords: Whether to include full polygon coordinates.
        include_features: Whether to include computed section features.
        include_top_matches: Whether to include template match rankings.
        reader_strategy: STEP reader order. Options: "flat_first", "xde_first", "flat_only", "xde_only".
        solid_filter: Optional callable (SolidInstance, index) → bool to skip solids.
    """

    # Section slicing
    num_sections: int = 5
    section_range: tuple[float, float] = (0.15, 0.85)

    # Classification
    template_accept_threshold: float = 0.12
    min_valid_sections: int = 3
    cluster_stability_ratio: float = 0.60

    # Output control
    max_vertices_export: int = 500
    include_vertices: bool = False
    include_polygon_coords: bool = True
    include_features: bool = True
    include_top_matches: bool = True

    # STEP reading
    reader_strategy: str = "flat_first"

    # Filtering
    solid_filter: object = None  # callable or None

    def section_fractions(self) -> tuple[float, ...]:
        """Compute evenly spaced section fractions within the configured range."""
        lo, hi = self.section_range
        if self.num_sections == 1:
            return ((lo + hi) / 2,)
        step = (hi - lo) / (self.num_sections - 1)
        return tuple(round(lo + i * step, 6) for i in range(self.num_sections))
