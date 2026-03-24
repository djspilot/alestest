#!/usr/bin/env python3
"""
Manufacturing Pipeline - convenience wrapper.

Usage:
    python run.py [args]          # Same as: python -m manufacturing_pipeline [args]

Quick mode (default):
    python run.py -f mypart.step          Analyze a single file
    python run.py --batch                 Batch process all files
    python run.py --aag -v                AAG analysis with verbose output

Full ISO pipeline:
    python run.py -f mypart.step --full   Complete ISO analysis with database

Step 0 classification only (geen pre-routing, geen geometry stages):
    python run.py --step0 mypart.step     STEP → BOM solids → classify_step0 per solid
"""
from collections import Counter
from collections import defaultdict
import os
import sys


def _load_step_bom_solids(step_file):
    """Load solids and aligned part names via STEP BOM-aware extraction.

    Primary path:
      XCAF tree traversal (solid-name pairs)

    Fallback path:
      CadQuery import with generated Part_### names
    """
    solids = []
    names = []
    source = "xcaf"
    warning = ""

    try:
        from manufacturing_pipeline.core.xcaf_reader import xcaf_match_solids_to_names

        xcaf_result = xcaf_match_solids_to_names(step_file)
        if xcaf_result is not None:
            solids, names = xcaf_result
    except Exception as exc:
        warning = f"XCAF load warning: {exc}"

    if solids:
        # Guard against mismatched lengths
        if len(names) < len(solids):
            names = list(names) + [f"Part_{idx + 1:03d}" for idx in range(len(names), len(solids))]
        elif len(names) > len(solids):
            names = list(names[: len(solids)])
        return solids, names, source, warning

    # Fallback: direct CadQuery load
    source = "cadquery-fallback"
    import cadquery as cq

    assembly = cq.importers.importStep(step_file)

    cq_solids = []
    try:
        if hasattr(assembly, "solids"):
            wp_solids = assembly.solids()
            if hasattr(wp_solids, "vals"):
                cq_solids = list(wp_solids.vals())
            else:
                cq_solids = list(wp_solids)
    except Exception:
        cq_solids = []

    if not cq_solids:
        if hasattr(assembly, "val"):
            cq_solids = [assembly.val()]
        else:
            cq_solids = [assembly]

    for obj in cq_solids:
        solids.append(obj.wrapped if hasattr(obj, "wrapped") else obj)

    names = [f"Part_{idx + 1:03d}" for idx in range(len(solids))]
    return solids, names, source, warning


def _ordered_bom_counts(names):
    """Create an ordered name->quantity map preserving first appearance order."""
    counts = {}
    for name in names:
        if name not in counts:
            counts[name] = 0
        counts[name] += 1
    return counts


def _print_step_trace(trace_result):
    """Render detailed Step 0 trace output."""
    final_result = trace_result.get("final_result", {})
    steps_info = trace_result.get("steps", [])

    for step_info in steps_info:
        step_num = step_info.get("step", "?")
        step_name = step_info.get("name", "?")
        verdict = step_info.get("verdict", "?")

        print(f"  STAP {step_num} - {step_name}")
        print(f"    Verdict: {verdict}")

        criteria = step_info.get("criteria", [])
        if criteria:
            print("    Criteria:")
            for crit in criteria:
                crit_name = crit.get("name", "?")
                crit_value = crit.get("value", "?")
                crit_pass = crit.get("pass", "?")

                if crit_pass is True:
                    symbol = "[OK]"
                elif crit_pass is False:
                    symbol = "[NO]"
                else:
                    symbol = " ? "

                print(f"      {symbol} {crit_name}: {crit_value}")

        note = step_info.get("note")
        if note:
            print(f"    Note: {note}")

        result_label = step_info.get("result")
        if result_label:
            print(f"    -> Resultaat: {result_label} STOP")
        else:
            next_step = step_info.get("next")
            if next_step:
                print(f"    -> Doorval naar {next_step}")

        print()

    print(f"  {'-' * 95}")
    final_label = final_result.get("label", "?")
    final_confidence = final_result.get("confidence", 0.0)
    final_method = final_result.get("method", "?")
    final_reason = final_result.get("reason", "")

    print(f"  FINAAL RESULTAAT: {final_label}")
    print(f"    Stap: {final_result.get('step', '?')}")
    print(f"    Methode: {final_method}")
    print(f"    Confidence: {final_confidence:.0%}")
    print(f"    Reden: {final_reason}")
    print(f"  {'-' * 95}\n")

    return final_label


def _run_step0_classification(step_files):
    """
    STEP -> BOM extraction -> classify_step0_detailed_trace per solid.

    Dit pad gebruikt bewust geen pre-routing en geen geometry stages.
    De solids + namen komen primair uit XCAF (assembly-aware).
    """
    from manufacturing_pipeline.analysis.classification import classify_step0_detailed_trace

    for step_file in step_files:
        if not os.path.exists(step_file):
            print(f"ERROR: bestand niet gevonden: {step_file}")
            continue

        assembly_name = os.path.splitext(os.path.basename(step_file))[0]
        print(f"\n{'=' * 95}")
        print(f"Step 0 Classificatie: {assembly_name}")
        print(f"Bestand: {step_file}")
        print(f"{'=' * 95}")

        try:
            solids, names, source, warning = _load_step_bom_solids(step_file)
        except Exception as exc:
            print(f"  FOUT bij laden STEP/BOM: {exc}")
            continue

        if not solids:
            print("  (geen solids gevonden)")
            continue

        if warning:
            print(f"  Waarschuwing: {warning}")

        bom_counts = _ordered_bom_counts(names)

        print(f"\n  Solid bron: {source}")
        print(f"  BOM regels: {len(bom_counts)}")
        print(f"  BOM stuks:  {len(solids)}")
        print("  BOM overzicht:")
        for row_idx, (part_name, qty) in enumerate(bom_counts.items(), 1):
            print(f"    [{row_idx:02d}] qty={qty:>3}  naam={part_name}")
        print(f"\n  {'-'*95}\n")

        seen_per_name = defaultdict(int)
        label_counter = Counter()

        for i, solid in enumerate(solids, 1):
            part_name = names[i - 1] if i - 1 < len(names) else f"Part_{i:03d}"
            seen_per_name[part_name] += 1
            instance_idx = seen_per_name[part_name]
            total_for_name = bom_counts.get(part_name, 1)

            print(f"  SOLIDE #{i} / {len(solids)}")
            print(f"  BOM item: {part_name} ({instance_idx}/{total_for_name})")
            print(f"  {'-'*95}\n")

            # Run detailed trace on this solid
            try:
                trace_result = classify_step0_detailed_trace(solid)

                if trace_result is None:
                    print("  (trace-functie geeft None terug)\n")
                    continue

                final_label = _print_step_trace(trace_result)
                label_counter[final_label] += 1

            except Exception as e_trace:
                import traceback
                print(f"  FOUT bij trace: {e_trace}")
                traceback.print_exc()
                print()

        if label_counter:
            print("  Label samenvatting:")
            for label, qty in label_counter.items():
                print(f"    - {label}: {qty}")

        print(f"\n  End of STEP 0 Analysis ({len(solids)} solid(s) processed)\n")


if __name__ == "__main__":
    if "--step0" in sys.argv:
        sys.argv.remove("--step0")
        step_files = [a for a in sys.argv[1:] if not a.startswith("-")]
        if not step_files:
            print("Gebruik: python run.py --step0 <step_bestand.step> [...]")
            sys.exit(1)
        _run_step0_classification(step_files)
    else:
        from manufacturing_pipeline.cli import main
        main()

