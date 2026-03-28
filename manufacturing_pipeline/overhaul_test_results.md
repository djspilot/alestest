# Overhaul Test Results

Branch: overhaul-of-shit-code
Test model: /Users/ds/AIdoel/alestest/nieuwmodel.step
Rule: after every phase commit, run the model test and record both automated and manual results.

## How To Use This Log

1. Finish one phase and create one commit.
2. Run:

```bash
export PYTHONPATH=/Users/ds/AIdoel/alestest
python /Users/ds/AIdoel/alestest/manufacturing_pipeline/cli.py -f /Users/ds/AIdoel/alestest/nieuwmodel.step
```

3. Add one new section using the template below.
4. Record the exact commit hash, command, exit code, and key output/error.
5. Add your manual test verdict and notes.

## Entry Template

```markdown
## Phase X - <title>
Date: YYYY-MM-DD HH:MM TZ
Commit: <hash> <message>
Command: python /Users/ds/AIdoel/alestest/manufacturing_pipeline/cli.py -f /Users/ds/AIdoel/alestest/nieuwmodel.step
Exit code: <0|non-zero>
Automated result: <pass/fail>
Key output:
- ...
Manual test result: <pass/fail>
Manual notes:
- ...
Next action:
- ...
```

## Baseline (Before Phase 1)
Date: 2026-03-28 15:56:48 CET
Commit: 661cf02 chore: snapshot current workspace changes
Command: python /Users/ds/AIdoel/alestest/manufacturing_pipeline/cli.py -f /Users/ds/AIdoel/alestest/nieuwmodel.step
Exit code: 1
Automated result: fail
Key output:
- ValueError: too many values to unpack (expected 2)
- Note: direct cli.py execution requires PYTHONPATH=/Users/ds/AIdoel/alestest
- File: manufacturing_pipeline/cli.py, function: run_quick, line around output_dir/part_name assignment
Manual test result: pending
Manual notes:
- Pending your manual validation after fix.
Next action:
- Fix quick mode call path so baseline model can run successfully before starting Phase 1 deletions.

## Baseline Retest (CLI Fixed)
Date: 2026-03-28 16:01:54 CET
Commit: 661cf02 chore: snapshot current workspace changes
Command: python /Users/ds/AIdoel/alestest/manufacturing_pipeline/cli.py -f /Users/ds/AIdoel/alestest/nieuwmodel.step
Exit code: 0
Automated result: pass
Key output:
- QUICK ANALYSIS: nieuwmodel
- Total runtime: 34.99s
- COMPLETE with report and output files generated
Manual test result: pending
Manual notes:
- Waiting for your manual verification on this successful baseline run.
Next action:
- Start Phase 1 deletions and repeat this exact CLI test after commit.
