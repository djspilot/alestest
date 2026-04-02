from __future__ import annotations

import os
import sys

from manufacturing_pipeline.vendor import freecad_sheetmetal


def vendor_sheetmetal_root() -> str:
    return os.path.dirname(freecad_sheetmetal.__file__)


def ensure_vendor_sheetmetal_on_sys_path() -> str:
    root = vendor_sheetmetal_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    return root

