"""
Pipeline Configuration Module

Allows enabling/disabling of analysis modules via CLI or config file.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
import json
import os


@dataclass
class ModuleConfig:
    """Configuration for individual analysis modules."""

    # Basic Analysis (always on by default)
    geometry: bool = True
    topology: bool = True
    holes: bool = True
    faces: bool = True

    # ISO Standards
    iso2768_tolerances: bool = True
    iso286_fits: bool = True
    iso68_threads: bool = True
    iso1302_surface: bool = True
    iso13715_edges: bool = True

    # Manufacturing
    mass_estimation: bool = True
    component_classification: bool = True
    detailed_parts: bool = True

    # Werkvoorbereiding (can be individually toggled)
    cost_estimation: bool = True
    tool_list: bool = True
    outsourcing: bool = True
    surface_treatment: bool = True
    purchase_spec: bool = True

    # Plaatwerk / Sheet Metal
    sheetmetal_analysis: bool = True
    bend_detection: bool = True
    kantbank_tooling: bool = True
    flat_pattern: bool = True

    # PDF Sections
    pdf_correlation: bool = True

    # Report options
    simple_cost_report: bool = True      # Eenvoudig kostenoverzicht per onderdeel
    detailed_iso_report: bool = False    # Gedetailleerd ISO rapport
    per_part_breakdown: bool = True      # Kosten per onderdeel uitsplitsen

    def to_dict(self) -> Dict[str, bool]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, bool]) -> "ModuleConfig":
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})

    def get_enabled_modules(self) -> list:
        """Return list of enabled module names."""
        return [k for k, v in self.to_dict().items() if v]

    def get_disabled_modules(self) -> list:
        """Return list of disabled module names."""
        return [k for k, v in self.to_dict().items() if not v]


@dataclass
class PricingConfig:
    """Configuration for hourly rates and material prices."""

    # CNC operations (€/hour)
    cnc_draaien_klein: float = 55.0
    cnc_draaien_middel: float = 65.0
    cnc_draaien_groot: float = 85.0
    cnc_frezen_3as: float = 60.0
    cnc_frezen_4as: float = 75.0
    cnc_frezen_5as: float = 95.0

    # Sheet metal (€/hour)
    laser_snijden: float = 70.0
    plasma_snijden: float = 55.0
    waterstraal: float = 85.0
    ponsen: float = 50.0
    kanten: float = 45.0
    lassen_mig: float = 50.0
    lassen_tig: float = 65.0

    # Finishing (€/hour)
    slijpen_vlak: float = 55.0
    slijpen_rond: float = 60.0
    ontbramen_hand: float = 35.0
    ontbramen_machine: float = 40.0

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "PricingConfig":
        # Filter only known fields and non-comment keys
        valid_data = {k: v for k, v in data.items()
                      if hasattr(cls, k) and not k.startswith('_')}
        return cls(**valid_data)


@dataclass
class MaterialPricesConfig:
    """Configuration for material prices (€/kg)."""

    steel_s235: float = 1.20
    steel_s355: float = 1.35
    steel_304: float = 4.50
    steel_316: float = 5.80
    steel_42crmo4: float = 2.20
    steel_c45: float = 1.80
    alu_6061: float = 3.50
    alu_6082: float = 3.80
    alu_7075: float = 8.50
    alu_5083: float = 4.20
    messing_cuzn39pb3: float = 7.50
    brons_cusn8: float = 12.0

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)

    def get_price(self, material: str) -> float:
        """Get price for material, with fallback to default."""
        return getattr(self, material, 1.50)

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "MaterialPricesConfig":
        valid_data = {k: v for k, v in data.items()
                      if hasattr(cls, k) and not k.startswith('_')}
        return cls(**valid_data)


@dataclass
class CostColumnsConfig:
    """Configuration for which cost columns to show in simple report."""

    snijden: bool = True
    ink_per_stuk: bool = True
    zagen: bool = True
    zetten: bool = True
    verspanen: bool = True
    logistiek: bool = True
    lassen: bool = True
    boren: bool = True
    assembleren: bool = True

    def to_dict(self) -> Dict[str, bool]:
        return asdict(self)

    def get_enabled_columns(self) -> list:
        """Return list of enabled column names."""
        return [k for k, v in self.to_dict().items() if v]

    @classmethod
    def from_dict(cls, data: Dict[str, bool]) -> "CostColumnsConfig":
        valid_data = {k: v for k, v in data.items()
                      if hasattr(cls, k) and not k.startswith('_')}
        return cls(**valid_data)


@dataclass
class PipelineConfig:
    """Full pipeline configuration."""

    # Input/Output
    step_file: str = ""
    pdf_file: Optional[str] = None
    output_dir: str = "."

    # Material & Quantity (for cost estimation)
    material: str = "steel_s235"
    quantity: int = 1
    surface_treatment: Optional[str] = None

    # Module settings
    modules: ModuleConfig = field(default_factory=ModuleConfig)

    # Pricing configuration
    hourly_rates: PricingConfig = field(default_factory=PricingConfig)
    material_prices: MaterialPricesConfig = field(default_factory=MaterialPricesConfig)

    # Cost columns for simple report
    cost_columns: CostColumnsConfig = field(default_factory=CostColumnsConfig)

    # Cache settings
    use_cache: bool = True
    cache_dir: str = ".pipeline_cache"
    from_stage: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        return result

    def save(self, filepath: str):
        """Save configuration to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "PipelineConfig":
        """Load configuration from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)

        # Extract nested configs
        modules_data = data.pop('modules', {})
        hourly_rates_data = data.pop('hourly_rates', {})
        material_prices_data = data.pop('material_prices', {})
        cost_columns_data = data.pop('cost_columns', {})

        # Filter out comment keys from main config
        filtered_data = {k: v for k, v in data.items()
                         if not k.startswith('_') and hasattr(cls, k)}

        config = cls(**filtered_data)
        config.modules = ModuleConfig.from_dict(modules_data)
        config.hourly_rates = PricingConfig.from_dict(hourly_rates_data)
        config.material_prices = MaterialPricesConfig.from_dict(material_prices_data)
        config.cost_columns = CostColumnsConfig.from_dict(cost_columns_data)
        return config


# Module groupings for easy enable/disable
MODULE_GROUPS = {
    "basic": ["geometry", "topology", "holes", "faces"],
    "iso": ["iso2768_tolerances", "iso286_fits", "iso68_threads", "iso1302_surface", "iso13715_edges"],
    "manufacturing": ["mass_estimation", "component_classification", "detailed_parts"],
    "werkvoorbereiding": ["cost_estimation", "tool_list", "outsourcing", "surface_treatment", "purchase_spec"],
    "plaatwerk": ["sheetmetal_analysis", "bend_detection", "kantbank_tooling", "flat_pattern"],
    "all": None,  # Special: all modules
}


# Human-readable module names (Dutch/English)
MODULE_NAMES = {
    "geometry": "Geometrie / Geometry",
    "topology": "Topologie / Topology",
    "holes": "Gaten detectie / Hole Detection",
    "faces": "Vlak analyse / Face Analysis",
    "iso2768_tolerances": "ISO 2768 Toleranties",
    "iso286_fits": "ISO 286 Passingen / Fits",
    "iso68_threads": "ISO 68-1 Schroefdraad / Threads",
    "iso1302_surface": "ISO 1302 Oppervlakteruwheid / Surface Finish",
    "iso13715_edges": "ISO 13715 Randen / Edges",
    "mass_estimation": "Massa schatting / Mass Estimation",
    "component_classification": "Component classificatie",
    "detailed_parts": "Gedetailleerde onderdelen / Detailed Parts",
    "cost_estimation": "Kostprijsberekening / Cost Estimation",
    "tool_list": "Gereedschapslijst / Tool List",
    "outsourcing": "Uitbesteding / Outsourcing",
    "surface_treatment": "Oppervlaktebehandeling / Surface Treatment",
    "purchase_spec": "Inkoop specificatie / Purchase Spec",
    "sheetmetal_analysis": "Plaatwerk Analyse / Sheet Metal Analysis",
    "bend_detection": "Buiging Detectie / Bend Detection",
    "kantbank_tooling": "Kantbank Gereedschap / Press Brake Tooling",
    "flat_pattern": "Uitslag Berekening / Flat Pattern",
    "pdf_correlation": "PDF Correlatie / PDF Correlation",
}


def create_default_config(step_file: str = "") -> PipelineConfig:
    """Create default configuration with all modules enabled."""
    return PipelineConfig(step_file=step_file)


def create_minimal_config(step_file: str = "") -> PipelineConfig:
    """Create minimal configuration (basic analysis only)."""
    config = PipelineConfig(step_file=step_file)
    # Disable advanced modules
    config.modules.iso2768_tolerances = False
    config.modules.iso286_fits = False
    config.modules.iso68_threads = False
    config.modules.iso1302_surface = False
    config.modules.iso13715_edges = False
    config.modules.cost_estimation = False
    config.modules.tool_list = False
    config.modules.outsourcing = False
    config.modules.surface_treatment = False
    config.modules.purchase_spec = False
    return config


def apply_module_toggles(config: ModuleConfig, enable: list = None, disable: list = None):
    """
    Apply module enable/disable toggles.

    Args:
        config: ModuleConfig to modify
        enable: List of module names or groups to enable
        disable: List of module names or groups to disable
    """
    enable = enable or []
    disable = disable or []

    def resolve_modules(names: list) -> list:
        """Resolve group names to individual modules."""
        result = []
        for name in names:
            if name in MODULE_GROUPS:
                if MODULE_GROUPS[name] is None:  # "all"
                    result.extend(MODULE_NAMES.keys())
                else:
                    result.extend(MODULE_GROUPS[name])
            else:
                result.append(name)
        return result

    # Apply enables first, then disables
    for module in resolve_modules(enable):
        if hasattr(config, module):
            setattr(config, module, True)

    for module in resolve_modules(disable):
        if hasattr(config, module):
            setattr(config, module, False)

    return config


def print_module_status(config: ModuleConfig):
    """Print current module status to console."""
    print("\n" + "="*50)
    print("MODULE CONFIGURATIE / MODULE CONFIGURATION")
    print("="*50)

    for group_name, modules in MODULE_GROUPS.items():
        if modules is None:
            continue
        print(f"\n[{group_name.upper()}]")
        for module in modules:
            status = "✓ AAN" if getattr(config, module, False) else "✗ UIT"
            name = MODULE_NAMES.get(module, module)
            print(f"  {status}  {name}")

    print("\n" + "="*50)
