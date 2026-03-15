# XML Status Workflow

Use this workflow to make sure generated XML stays valid and is not lost.

## Goal

- Always validate XML status fields after generation
- Keep timestamped snapshots in a commitable folder
- Let teammates reproduce and review exact XML state

## One-click command (Windows PowerShell)

From workspace root:

```powershell
powershell -ExecutionPolicy Bypass -File alestest/scripts/run_xml_status_pipeline.ps1 \
  -Step stepfiles/10040878_1.stp \
  -Tag team-run-20260315 \
  -FailOnWarning
```

Optional parameters:

- `-Reference <path-to-reference-xml>`
- `-Output <path-to-output-xml>`
- `-Material steel_s235` (default)

## What the command does

1. Generates XML via `scripts/generate_xml_dxf.py`
2. Validates critical status in `scripts/preserve_xml_status.py`
3. Saves snapshot to `snapshots/xml_status/<xml_stem>/<timestamp>/`
4. Writes pointer file: `snapshots/xml_status/LATEST_<xml_stem>.txt`
5. Stores metadata (`meta.json`) with git branch/commit and validation summary

## Validation rules

Hard fail:

- Any sheet row without `Sheet_BoxX` or `Sheet_BoxY`

Warning:

- `Sheet_NrBends > 0` while `Sheet_UnfoldSuccess != True`
- Missing `DocumentControl`
- Empty `DocumentControl/Status`

With `-FailOnWarning`, warnings also return exit code `1`.

## Team practice (recommended)

1. Run the one-click command for each STEP test file.
2. Commit code changes and (when needed) snapshot folders for milestone runs.
3. Push to GitHub so others can inspect the same XML state.
4. Before pull/rebase, ensure your run is committed or stashed.

## Snapshot location

Snapshots are stored in:

- `snapshots/xml_status/`

This location is intentionally outside `data/output/` so it is not ignored by default.
