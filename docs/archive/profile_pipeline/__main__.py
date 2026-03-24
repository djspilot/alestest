"""CLI entrypoint: python -m profile_pipeline model.stp"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import PipelineConfig
from .pipeline import classify_step_file


def main():
    parser = argparse.ArgumentParser(
        prog="profile_pipeline",
        description="Classify steel profiles from STEP files.",
    )
    parser.add_argument("step_file", help="Path to .stp/.step file")
    parser.add_argument("-o", "--output", help="Output JSON path")
    parser.add_argument("-n", "--num-sections", type=int, default=5, help="Number of cross-sections (default: 5)")
    parser.add_argument("--range-start", type=float, default=0.15, help="Section range start fraction (default: 0.15)")
    parser.add_argument("--range-end", type=float, default=0.85, help="Section range end fraction (default: 0.85)")
    parser.add_argument("--threshold", type=float, default=0.12, help="Template match threshold (default: 0.12)")
    parser.add_argument("--include-vertices", action="store_true", help="Include 3D vertices in output")
    parser.add_argument("--no-polygons", action="store_true", help="Exclude polygon coordinates")
    parser.add_argument("--no-features", action="store_true", help="Exclude section features")
    parser.add_argument("--reader", choices=["flat_first", "xde_first", "flat_only", "xde_only"], default="flat_first")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    # Logging
    level = logging.DEBUG if args.verbose else (logging.WARNING if args.quiet else logging.INFO)
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    config = PipelineConfig(
        num_sections=args.num_sections,
        section_range=(args.range_start, args.range_end),
        template_accept_threshold=args.threshold,
        include_vertices=args.include_vertices,
        include_polygon_coords=not args.no_polygons,
        include_features=not args.no_features,
        reader_strategy=args.reader,
    )

    output_path = args.output
    if output_path is None:
        from pathlib import Path
        output_path = Path(args.step_file).with_suffix(".classified.json")

    results = classify_step_file(args.step_file, config=config, output_json=output_path)

    # Summary to stdout
    print(f"\n{'='*50}")
    print(f"  {len(results)} solid(s) geclassificeerd")
    print(f"{'='*50}")
    for r in results:
        print(f"  {r.name:30s}  →  {r.classification.label}")
    print(f"\n  Output: {output_path}")


if __name__ == "__main__":
    main()
