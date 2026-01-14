"""
Cache Manager for Manufacturing Pipeline

Provides checkpoint/resume functionality to avoid recomputing expensive operations.
Saves intermediate results to disk and allows resuming from any stage.
"""

import os
import json
import pickle
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from enum import Enum


class PipelineStage(Enum):
    """Pipeline execution stages"""
    LOAD_STEP = "load_step"
    DETECT_HOLES = "detect_holes"
    GEOMETRY_ANALYSIS = "geometry_analysis"
    FACE_ANALYSIS = "face_analysis"
    TOPOLOGY = "topology"
    COMPONENT_CLASSIFICATION = "component_classification"
    DETAILED_PARTS = "detailed_parts"
    MANUFACTURING_REQUIREMENTS = "manufacturing_requirements"
    HOLES_WITH_FITS = "holes_with_fits"
    THREADS = "threads"
    CHAMFERS_FILLETS = "chamfers_fillets"
    MASS_PROPERTIES = "mass_properties"
    WERKVOORBEREIDING = "werkvoorbereiding"
    SHEETMETAL = "sheetmetal"
    ASSEMBLY_BOM = "assembly_bom"
    PDF_CORRELATION = "pdf_correlation"
    COMPLETE = "complete"


# Define stage dependencies (what must be completed before each stage)
STAGE_DEPENDENCIES = {
    PipelineStage.LOAD_STEP: [],
    PipelineStage.DETECT_HOLES: [PipelineStage.LOAD_STEP],
    PipelineStage.GEOMETRY_ANALYSIS: [PipelineStage.LOAD_STEP],
    PipelineStage.FACE_ANALYSIS: [PipelineStage.LOAD_STEP],
    PipelineStage.TOPOLOGY: [PipelineStage.LOAD_STEP],
    PipelineStage.COMPONENT_CLASSIFICATION: [PipelineStage.LOAD_STEP],
    PipelineStage.DETAILED_PARTS: [PipelineStage.LOAD_STEP],
    PipelineStage.MANUFACTURING_REQUIREMENTS: [PipelineStage.FACE_ANALYSIS, PipelineStage.GEOMETRY_ANALYSIS],
    PipelineStage.HOLES_WITH_FITS: [PipelineStage.DETECT_HOLES],
    PipelineStage.THREADS: [PipelineStage.DETECT_HOLES],
    PipelineStage.CHAMFERS_FILLETS: [PipelineStage.LOAD_STEP],
    PipelineStage.MASS_PROPERTIES: [PipelineStage.GEOMETRY_ANALYSIS],
    PipelineStage.WERKVOORBEREIDING: [PipelineStage.DETECT_HOLES, PipelineStage.THREADS, PipelineStage.CHAMFERS_FILLETS],
    PipelineStage.SHEETMETAL: [PipelineStage.GEOMETRY_ANALYSIS, PipelineStage.FACE_ANALYSIS],
    PipelineStage.ASSEMBLY_BOM: [PipelineStage.LOAD_STEP, PipelineStage.COMPONENT_CLASSIFICATION],
    PipelineStage.PDF_CORRELATION: [PipelineStage.DETECT_HOLES],
    PipelineStage.COMPLETE: list(PipelineStage)[:-1],  # All stages except COMPLETE
}


@dataclass
class CacheMetadata:
    """Metadata about cached data"""
    step_file: str
    step_file_hash: str
    created_at: str
    stages_completed: List[str]
    last_stage: str
    pipeline_version: str = "2.0"


class CacheManager:
    """Manages caching of pipeline intermediate results"""

    def __init__(self, cache_dir: str = ".pipeline_cache"):
        self.cache_dir = cache_dir
        self.metadata_file = os.path.join(cache_dir, "metadata.json")
        self.data_cache: Dict[str, Any] = {}
        self._ensure_cache_dir()

    def _ensure_cache_dir(self):
        """Create cache directory if it doesn't exist"""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def _get_file_hash(self, filepath: str) -> str:
        """Calculate MD5 hash of a file for change detection"""
        if not os.path.exists(filepath):
            return ""
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            # Read in chunks for large files
            for chunk in iter(lambda: f.read(65536), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _get_stage_file(self, stage: PipelineStage) -> str:
        """Get the cache file path for a stage"""
        return os.path.join(self.cache_dir, f"{stage.value}.pkl")

    def _load_metadata(self) -> Optional[CacheMetadata]:
        """Load cache metadata"""
        if not os.path.exists(self.metadata_file):
            return None
        try:
            with open(self.metadata_file, 'r') as f:
                data = json.load(f)
                return CacheMetadata(**data)
        except Exception:
            return None

    def _save_metadata(self, metadata: CacheMetadata):
        """Save cache metadata"""
        with open(self.metadata_file, 'w') as f:
            json.dump(asdict(metadata), f, indent=2)

    def is_cache_valid(self, step_file: str) -> bool:
        """Check if cache is valid for the given STEP file"""
        metadata = self._load_metadata()
        if metadata is None:
            return False

        current_hash = self._get_file_hash(step_file)
        return (metadata.step_file == step_file and
                metadata.step_file_hash == current_hash)

    def get_completed_stages(self) -> List[PipelineStage]:
        """Get list of completed stages from cache"""
        metadata = self._load_metadata()
        if metadata is None:
            return []
        return [PipelineStage(s) for s in metadata.stages_completed]

    def get_last_stage(self) -> Optional[PipelineStage]:
        """Get the last completed stage"""
        metadata = self._load_metadata()
        if metadata is None or not metadata.last_stage:
            return None
        return PipelineStage(metadata.last_stage)

    def can_resume_from(self, stage: PipelineStage) -> bool:
        """Check if we can resume from a specific stage"""
        completed = self.get_completed_stages()
        dependencies = STAGE_DEPENDENCIES.get(stage, [])
        return all(dep in completed for dep in dependencies)

    def save_stage(self, stage: PipelineStage, data: Any, step_file: str):
        """Save data for a completed stage"""
        # Save the data
        stage_file = self._get_stage_file(stage)
        with open(stage_file, 'wb') as f:
            pickle.dump(data, f)

        # Update in-memory cache
        self.data_cache[stage.value] = data

        # Update metadata
        metadata = self._load_metadata()
        if metadata is None:
            metadata = CacheMetadata(
                step_file=step_file,
                step_file_hash=self._get_file_hash(step_file),
                created_at=datetime.now().isoformat(),
                stages_completed=[],
                last_stage=""
            )

        if stage.value not in metadata.stages_completed:
            metadata.stages_completed.append(stage.value)
        metadata.last_stage = stage.value
        self._save_metadata(metadata)

    def load_stage(self, stage: PipelineStage) -> Optional[Any]:
        """Load data for a stage from cache"""
        # Check in-memory cache first
        if stage.value in self.data_cache:
            return self.data_cache[stage.value]

        # Load from disk
        stage_file = self._get_stage_file(stage)
        if not os.path.exists(stage_file):
            return None

        try:
            with open(stage_file, 'rb') as f:
                data = pickle.load(f)
                self.data_cache[stage.value] = data
                return data
        except Exception as e:
            print(f"Warning: Could not load cached stage {stage.value}: {e}")
            return None

    def has_stage(self, stage: PipelineStage) -> bool:
        """Check if a stage is cached"""
        return stage in self.get_completed_stages()

    def clear_cache(self):
        """Clear all cached data"""
        import shutil
        if os.path.exists(self.cache_dir):
            shutil.rmtree(self.cache_dir)
        self.data_cache.clear()
        self._ensure_cache_dir()

    def clear_from_stage(self, stage: PipelineStage):
        """Clear cache from a specific stage onwards"""
        metadata = self._load_metadata()
        if metadata is None:
            return

        # Find all stages that depend on this stage (directly or indirectly)
        stages_to_clear = [stage]
        for s in PipelineStage:
            deps = STAGE_DEPENDENCIES.get(s, [])
            if stage in deps or any(d in stages_to_clear for d in deps):
                stages_to_clear.append(s)

        # Remove the stage files and update metadata
        for s in stages_to_clear:
            stage_file = self._get_stage_file(s)
            if os.path.exists(stage_file):
                os.remove(stage_file)
            if s.value in self.data_cache:
                del self.data_cache[s.value]
            if s.value in metadata.stages_completed:
                metadata.stages_completed.remove(s.value)

        # Update last stage
        if metadata.stages_completed:
            metadata.last_stage = metadata.stages_completed[-1]
        else:
            metadata.last_stage = ""

        self._save_metadata(metadata)

    def get_status_report(self) -> str:
        """Get a human-readable status report of the cache"""
        metadata = self._load_metadata()
        if metadata is None:
            return "No cache found."

        lines = [
            "Pipeline Cache Status",
            "=" * 40,
            f"STEP File: {metadata.step_file}",
            f"File Hash: {metadata.step_file_hash[:16]}...",
            f"Created: {metadata.created_at}",
            f"Last Stage: {metadata.last_stage}",
            "",
            "Completed Stages:",
        ]

        all_stages = list(PipelineStage)
        for stage in all_stages:
            status = "✓" if stage.value in metadata.stages_completed else "○"
            lines.append(f"  {status} {stage.value}")

        return "\n".join(lines)


class PipelineRunner:
    """
    Pipeline runner with caching support.
    Runs only the stages that haven't been completed yet.
    """

    def __init__(self, step_file: str, cache_dir: str = ".pipeline_cache",
                 force_from: Optional[PipelineStage] = None,
                 no_cache: bool = False, verbose: bool = True):
        self.step_file = step_file
        self.cache = CacheManager(cache_dir)
        self.no_cache = no_cache
        self.force_from = force_from
        self.verbose = verbose

        # If force_from is set, clear cache from that stage
        if force_from and not no_cache:
            self.cache.clear_from_stage(force_from)

        # If cache is invalid for this file, clear it
        if not no_cache and not self.cache.is_cache_valid(step_file):
            if self.verbose:
                print(f"Cache invalid (file changed), starting fresh...")
            self.cache.clear_cache()

    def should_run_stage(self, stage: PipelineStage) -> bool:
        """Determine if a stage needs to be run"""
        if self.no_cache:
            return True
        return not self.cache.has_stage(stage)

    def get_or_run(self, stage: PipelineStage, run_func, *args, **kwargs) -> Any:
        """Get cached result or run the function"""
        if not self.should_run_stage(stage):
            cached = self.cache.load_stage(stage)
            if cached is not None:
                if self.verbose:
                    print(f"  [{stage.value}] Loaded from cache")
                return cached

        # Run the function
        if self.verbose:
            print(f"  [{stage.value}] Computing...")
        result = run_func(*args, **kwargs)

        # Cache the result
        if not self.no_cache:
            self.cache.save_stage(stage, result, self.step_file)

        return result

    def status(self) -> str:
        """Get cache status"""
        return self.cache.get_status_report()
