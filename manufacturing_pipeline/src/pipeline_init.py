"""
Pipeline initialization utilities.

Handles CLI argument normalization, path resolution, config loading,
and early-exit command handling.
"""
import os
from typing import Optional, Tuple

from .config import PipelineConfig, apply_module_toggles, print_module_status, MODULE_GROUPS, MODULE_NAMES
from .cache_manager import CacheManager, PipelineStage


def normalize_args(args) -> None:
    """Apply argument implications (e.g., --production-only sets other flags)."""
    if getattr(args, 'production_only', False):
        args.production_info = True
        args.no_report = True


def resolve_input_paths(step_arg: str, pdf_arg: Optional[str] = None) -> Tuple[str, str]:
    """Resolve STEP and PDF file paths."""
    step_file = step_arg
    pdf_file = pdf_arg or step_file.replace(".step", ".pdf").replace(".STEP", ".pdf")
    return step_file, pdf_file


def resolve_db_paths(base_dir: Optional[str] = None) -> Tuple[str, str]:
    """Resolve database and schema paths."""
    if base_dir is None:
        base_dir = os.path.dirname(os.path.dirname(__file__))
    db_path = "manufacturing_data.db"
    schema_path = os.path.join(base_dir, 'sql', 'schema.sql')
    return db_path, schema_path


def load_or_init_pipeline_config(args, step_file: str, base_dir: Optional[str] = None) -> PipelineConfig:
    """Load pipeline configuration from file or create default."""
    if base_dir is None:
        base_dir = os.path.dirname(os.path.dirname(__file__))
    
    default_config_path = os.path.join(base_dir, "pipeline_config.json")
    config_path = getattr(args, 'config', None) or (default_config_path if os.path.exists(default_config_path) else None)

    production_only = getattr(args, 'production_only', False)
    
    if config_path and os.path.exists(config_path):
        config = PipelineConfig.load(config_path)
        if not production_only:
            print(f"✓ Configuratie geladen uit: {config_path}")
    else:
        config = PipelineConfig(step_file=step_file)
        if not production_only:
            print("  (Geen config bestand gevonden, standaard instellingen gebruikt)")

    # Apply enable/disable toggles
    enable_list = getattr(args, 'enable', []) or []
    disable_list = getattr(args, 'disable', []) or []
    if enable_list or disable_list:
        apply_module_toggles(config.modules, enable_list, disable_list)

    # Update config with CLI args
    if hasattr(args, 'material'):
        config.material = args.material
    if hasattr(args, 'quantity'):
        config.quantity = args.quantity

    return config


def handle_module_listing(args) -> bool:
    """Handle --list-modules command. Returns True if handled (should exit)."""
    if not getattr(args, 'list_modules', False):
        return False
    
    print("\nBeschikbare Modules / Available Modules:")
    print("=" * 55)
    for group_name, modules in MODULE_GROUPS.items():
        if modules is None:
            continue
        print(f"\n[{group_name.upper()}]")
        for module in modules:
            name = MODULE_NAMES.get(module, module)
            print(f"  {module:25s} - {name}")
    print("\n" + "=" * 55)
    print("Gebruik / Usage:")
    print("  --enable <module|group>   Enable module or group")
    print("  --disable <module|group>  Disable module or group")
    return True


def handle_stage_listing(args) -> bool:
    """Handle --list-stages command. Returns True if handled."""
    if not getattr(args, 'list_stages', False):
        return False
    
    print("Pipeline Stages:")
    print("-" * 40)
    for stage in PipelineStage:
        print(f"  {stage.value}")
    return True


def handle_config_display_and_save(args, config: PipelineConfig) -> bool:
    """Handle --show-config and --save-config commands. Returns True if handled."""
    if getattr(args, 'show_config', False):
        print_module_status(config.modules)
        return True
    
    if getattr(args, 'save_config', None):
        config.save(args.save_config)
        print(f"Configuration saved to {args.save_config}")
        return True
    
    return False


def handle_cache_commands(args, cache: CacheManager) -> bool:
    """Handle --status and --clear-cache commands. Returns True if handled."""
    if getattr(args, 'status', False):
        print(cache.get_status_report())
        return True
    
    if getattr(args, 'clear_cache', False):
        cache.clear_cache()
        print("Cache cleared.")
        return True
    
    return False


def parse_force_from_stage(from_stage_str: Optional[str]) -> Optional[PipelineStage]:
    """Parse --from stage argument. Returns None if not specified or on error."""
    if not from_stage_str:
        return None
    
    try:
        stage = PipelineStage(from_stage_str)
        print(f"Will re-run from stage: {stage.value}")
        return stage
    except ValueError:
        print(f"Error: Unknown stage '{from_stage_str}'")
        print("Use --list-stages to see available stages.")
        return None
