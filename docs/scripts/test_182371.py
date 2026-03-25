"""Quick diagnostic for 10000550594 round shaft."""
from manufacturing_pipeline.core.xcaf_reader import xcaf_match_solids_to_names
from manufacturing_pipeline.analysis.classification import classify_step0_detailed_trace

step = r"data/stepfile/profiel/10000550594_Rev_01.stp"
items = xcaf_match_solids_to_names(step)
solid = items[0][0] if isinstance(items[0], (list, tuple)) else items[0]

out = classify_step0_detailed_trace(solid)
result = out["final_result"]
print("label:", result["label"])
print("step:", result["step"])
print("reason:", result["reason"])
print("fallthrough:", result["fallthrough"])

for step_info in out.get("steps", []):
    if step_info.get("step") == "0.1":
        print("\n--- STEP 0.1 criteria ---")
        for crit in step_info.get("criteria", []):
            print(f"  [{crit.get('pass')}] {crit.get('name')}: {crit.get('value')}")
