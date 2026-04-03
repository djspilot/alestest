# Server-Side Unfold Plan

## Goal

Keep the normal analysis pipeline responsive on `api.aidoel.nl`, while allowing operators to trigger a separate server-side unfold run for completed jobs.

## Implemented MVP

- Analysis jobs keep the uploaded source STEP instead of deleting it immediately.
- Completed jobs expose a separate unfold lifecycle:
  - `idle`
  - `queued`
  - `processing`
  - `completed`
  - `failed`
- New endpoints:
  - `POST /api/v1/jobs/{job_id}/unfold`
  - `GET /api/v1/jobs/{job_id}/unfold`
  - `GET /api/v1/jobs/{job_id}/unfold/artifacts/flat-step`
  - `GET /api/v1/jobs/{job_id}/unfold/artifacts/dxf`
- The API dashboard now shows an `Unfold` action next to completed files and exposes artifact links when available.

## Production Runtime Requirement

The current lite VPS image intentionally disables unfold. To enable server-side unfold in production, deploy the API with the full FreeCAD-capable image based on `Dockerfile.api` instead of `Dockerfile.api.lite`.

Required production characteristics:

- `FreeCAD`
- vendored `SheetMetalUnfolder`
- persistent upload storage
- persistent database path
- enough disk for generated `flat.step` and `dxf` artifacts

## Recommended Deployment Shape

### Option A: Single full API service

- Replace the current lite API image with the full image.
- The same API process handles:
  - upload + analysis
  - on-demand unfold

Pros:

- simplest operational model
- no cross-service routing

Cons:

- heavier image
- heavier memory footprint on the main API service

### Option B: Dedicated unfold worker service

- Keep the public API service lightweight.
- Run a second internal service or worker with the full runtime.
- Public API stores/queues unfold requests.
- Worker consumes queued unfold jobs and writes artifacts/results back.

Pros:

- safer scaling boundary
- isolates FreeCAD failures from the main API

Cons:

- more moving parts

## Performance Optimization Plan

### 1. Persistent FreeCAD worker pool

Use a bounded pool of long-lived FreeCAD workers instead of cold-spawning FreeCAD for each unfold request.

Target:

- start with `1` worker on small VPS
- move to `2` only if memory allows

### 2. Artifact caching by file hash

Cache successful unfold results by:

- STEP file hash
- relevant threshold config
- runtime/unfolder version

If the same file is re-unfolded, return cached artifacts immediately.

### 3. Queue unfold separately from analysis

Do not put unfold back into the default analysis path. Keep it opt-in and asynchronous.

### 4. Pre-warm runtime imports

On service startup, verify:

- `FreeCAD`
- `Part`
- `SheetMetalUnfolder`

This cuts the worst cold-start latency and surfaces runtime problems early.

### 5. Persist profiling per unfold stage

Capture timings for:

- STEP load
- base face selection
- sheet tree construction
- bend analysis
- unfold generation
- flat STEP export
- DXF export

Without stage timings, performance tuning will be guesswork.

### 6. Reuse source files and artifacts

Do not regenerate or relocate files unnecessarily.

- keep original uploaded STEP
- keep successful unfold artifacts
- clean only by retention policy

### 7. Add operational limits

- max concurrent unfold jobs
- max artifact retention age
- max storage per job/artifact set

This prevents a single VPS from being swamped by large CAD jobs.

## Next Engineering Steps

1. Switch production deploy from lite image to full FreeCAD image.
2. Add profiling around `run_unfold_to_step(...)`.
3. Add cache lookup by `file_hash`.
4. Add a bounded worker-pool abstraction for unfold execution.
5. Optionally split unfold into a dedicated internal worker service.
