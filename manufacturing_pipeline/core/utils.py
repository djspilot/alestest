"""Compatibility shim -- imports forwarded to specific submodules.

Prefer importing from the specific submodule directly:
  - paths: PROJECT_ROOT, DATA_DIR, etc.
  - cache: get_file_hash, load_cache, etc.
  - file_utils: find_step_files, get_output_dir, etc.
  - runtime_analysis: run_analysis
  - runtime_reporting: run_debug
"""

# Keep backward-compat for any external/script imports we may have missed.
from manufacturing_pipeline.core.paths import *  # noqa: F401,F403
from manufacturing_pipeline.core.runtime_analysis import run_analysis  # noqa: F401
from manufacturing_pipeline.core.runtime_reporting import run_debug  # noqa: F401
from manufacturing_pipeline.core.cache import (  # noqa: F401
    get_file_hash, load_cache, save_cache, get_cached_result, cache_result, CACHE_FILE,
)
from manufacturing_pipeline.core.file_utils import (  # noqa: F401
    find_step_files, select_step_file, get_output_dir, process_single_file, process_batch,
)
