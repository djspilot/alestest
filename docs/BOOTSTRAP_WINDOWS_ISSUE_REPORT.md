# Bootstrap Windows Incident Report (single-machine)

## Context
On this machine, running `bootstrap-windows.bat` initially failed while other machines worked.

## Observed failures
1. FreeCAD runtime bootstrap intermittently failed with:
   - `Bootstrap van micromamba gefaald: [WinError 5] Toegang geweigerd`
2. Runtime doctor schema mismatch in PowerShell script:
   - script expected `configured`
   - doctor output provided `configured_runtime`
3. Viewer dependency install failed on peer dependency conflicts:
   - `npm ERR! code ERESOLVE`
4. `npm list vite` returned `ELSPROBLEMS` even when Vite was actually runnable.

## Why this is machine-sensitive
- Package manager/bootstrap timing and file locks can vary per Windows machine.
- npm peer resolution outcomes can differ by lock state, npm version, and local cache.
- Strict schema assumptions in bootstrap scripts break when tool output evolves.

## Resilience changes applied
1. Doctor output compatibility:
   - `scripts/bootstrap-windows.ps1` now supports both `configured` and `configured_runtime`.
2. Viewer install fallback:
   - If `npm install` fails, retry with `npm install --legacy-peer-deps`.
3. Vite verification hardening:
   - Replaced `npm list vite` checks with `npm exec -- vite --version`.

## Validation on this machine
- `bootstrap-windows.bat` now completes end-to-end.
- FreeCAD runtime doctor verifies successfully.
- Vite starts successfully (`npm run dev`).

## Recommendation for maintainers
- Keep bootstrap tolerant to evolving JSON schemas from runtime tools.
- Treat npm peer-conflict checks as non-fatal when runtime command verification passes.
- Prefer executable checks (`npm exec -- vite --version`) over package tree checks (`npm list`).
