"""Regression test for Step 0 classification — 8 key files."""
import sys
from manufacturing_pipeline.core.xcaf_reader import xcaf_match_solids_to_names
from manufacturing_pipeline.analysis.classification import classify_step0

EXPECTED = [
    # (step_path, expected_label, description)
    # None label = only log, no explicit expectation
    ("data/stepfile/profiel/803143-7401.step",       "RECHTHOEKIGE_KOKER", "rechthoekige koker"),
    ("data/stepfile/profiel/10000550594_Rev_01.stp",  "ANDERS",             "ronde as (axiale check)"),
    ("data/stepfile/profiel/803041-7028.stp",         None,                 "step0=PLAAT(fallthrough) → classify_solid→ANDERS"),
    ("data/stepfile/profiel/10000182371_Rev_01.step",  "ANDERS",             "bewerkte ronde as – NEW"),
    ("data/stepfile/profiel/333380_rev[B].STEP",      "RONDE_BUIS",         "ronde buis"),
    ("data/stepfile/profiel/90181670_1-9.stp",        None,                 "ronde buis/anders – info only"),
    ("data/stepfile/profiel/05-01-5340.STEP",         None,                 "profiel – any non-error"),
    ("data/stepfile/profiel/803143-7015.stp",         None,                 "profiel – info only"),
    ("data/stepfile/profiel/10000804001_Rev_00.step",  None,                 "info only"),
]

ok = 0
fail = 0
skip = 0
for path, expected, desc in EXPECTED:
    try:
        items = xcaf_match_solids_to_names(path)
        solid = items[0][0] if isinstance(items[0], (list, tuple)) else items[0]
        res = classify_step0(solid)
        label = res["label"]
        step = res["step"]
        if expected is None:
            print(f"  OK (info) {path.split('/')[-1]:45s} → {label:22s} step={step}  # {desc}")
            ok += 1
        elif label == expected:
            print(f"  OK       {path.split('/')[-1]:45s} → {label:22s} step={step}  # {desc}")
            ok += 1
        else:
            print(f"  FAIL     {path.split('/')[-1]:45s} → {label:22s} (expected {expected}) step={step} reason={res['reason']}")
            fail += 1
    except FileNotFoundError:
        print(f"  SKIP     {path.split('/')[-1]:45s} (file not found)")
        skip += 1
    except Exception as exc:
        print(f"  ERROR    {path.split('/')[-1]:45s} : {exc}")
        fail += 1

print(f"\nResult: {ok} OK, {fail} FAIL, {skip} SKIP")
sys.exit(0 if fail == 0 else 1)
