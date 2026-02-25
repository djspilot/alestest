"""
Pipeline configuratie module

Maakt in- en uitschakelen van analysemodule(s) mogelijk via CLI of configbestand.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
import json
import os
import sys


@dataclass
class SystemConfig:
    """Systeemconfiguratie (paden, omgeving)."""
    freecad_path: str = "/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app"

    @property
    def freecad_python(self) -> str:
        """Pad naar de Python executable van FreeCAD."""
        # Mac OS specifieke padopbouw
        if sys.platform == 'darwin':
            return os.path.join(self.freecad_path, "Contents/Resources/bin/python")
        else:
            # Linux/Windows aanname (kan worden verfijnd)
            return os.path.join(self.freecad_path, "bin", "python")

    @property
    def freecad_lib(self) -> str:
        """Pad naar de bibliotheek van FreeCAD."""
        if sys.platform == 'darwin':
            return os.path.join(self.freecad_path, "Contents/Resources/lib")
        else:
            return os.path.join(self.freecad_path, "lib")

    @property
    def freecad_mod(self) -> str:
        """Pad naar de Mod-map van FreeCAD."""
        if sys.platform == 'darwin':
            return os.path.join(self.freecad_path, "Contents/Resources/Mod")
        else:
            return os.path.join(self.freecad_path, "Mod")

    @classmethod
    def from_env(cls) -> "SystemConfig":
        """Laad uit omgevingsvariabelen."""
        path = os.environ.get("FREECAD_PATH")
        if path:
            return cls(freecad_path=path)
        return cls()

    def to_dict(self) -> Dict[str, str]:
        return {"freecad_path": self.freecad_path}

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "SystemConfig":
        return cls(freecad_path=data.get("freecad_path", "/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app"))


@dataclass
class ModuleConfig:
    """Configuratie voor individuele analysemodule."""

    # Basisanalyse (standaard altijd aan)
    geometry: bool = True
    topology: bool = True
    holes: bool = True
    faces: bool = True

    # ISO-standaarden
    iso2768_tolerances: bool = True
    iso286_fits: bool = True
    iso68_threads: bool = True
    iso1302_surface: bool = True
    iso13715_edges: bool = True

    # Productie
    mass_estimation: bool = True
    component_classification: bool = True
    detailed_parts: bool = True

    # Werkvoorbereiding (kan individueel aan/uit)
    cost_estimation: bool = True
    tool_list: bool = True
    outsourcing: bool = True
    surface_treatment: bool = True
    purchase_spec: bool = True

    # Plaatwerk
    sheetmetal_analysis: bool = True
    bend_detection: bool = True
    kantbank_tooling: bool = True
    flat_pattern: bool = True

    # PDF-secties
    pdf_correlation: bool = True

    # Rapportopties
    simple_cost_report: bool = True      # Eenvoudig kostenoverzicht per onderdeel
    detailed_iso_report: bool = False    # Gedetailleerd ISO rapport
    per_part_breakdown: bool = True      # Kosten per onderdeel uitsplitsen

    def to_dict(self) -> Dict[str, bool]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, bool]) -> "ModuleConfig":
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})

    def get_enabled_modules(self) -> list:
        """Geef lijst met ingeschakelde modulenamen terug."""
        return [k for k, v in self.to_dict().items() if v]

    def get_disabled_modules(self) -> list:
        """Geef lijst met uitgeschakelde modulenamen terug."""
        return [k for k, v in self.to_dict().items() if not v]


@dataclass
class PricingConfig:
    """Configuratie voor uurtarieven en materiaalprijzen."""

    # CNC-bewerkingen (€/uur)
    cnc_draaien_klein: float = 55.0
    cnc_draaien_middel: float = 65.0
    cnc_draaien_groot: float = 85.0
    cnc_frezen_3as: float = 60.0
    cnc_frezen_4as: float = 75.0
    cnc_frezen_5as: float = 95.0

    # Plaatwerk (€/uur)
    laser_snijden: float = 70.0
    plasma_snijden: float = 55.0
    waterstraal: float = 85.0
    ponsen: float = 50.0
    kanten: float = 45.0
    lassen_mig: float = 50.0
    lassen_tig: float = 65.0

    # Nabewerking (€/uur)
    slijpen_vlak: float = 55.0
    slijpen_rond: float = 60.0
    ontbramen_hand: float = 35.0
    ontbramen_machine: float = 40.0

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "PricingConfig":
        # Filter alleen bekende velden en geen commentaar-sleutels
        valid_data = {k: v for k, v in data.items()
                      if hasattr(cls, k) and not k.startswith('_')}
        return cls(**valid_data)


@dataclass
class MaterialPricesConfig:
    """Configuratie voor materiaalprijzen (€/kg)."""

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
        """Geef prijs voor materiaal terug, met fallback naar standaard."""
        return getattr(self, material, 1.50)

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "MaterialPricesConfig":
        valid_data = {k: v for k, v in data.items()
                      if hasattr(cls, k) and not k.startswith('_')}
        return cls(**valid_data)


@dataclass
class CostColumnsConfig:
    """Configuratie voor kostenkolommen in eenvoudig rapport."""

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
        """Geef lijst met ingeschakelde kolomnamen terug."""
        return [k for k, v in self.to_dict().items() if v]

    @classmethod
    def from_dict(cls, data: Dict[str, bool]) -> "CostColumnsConfig":
        valid_data = {k: v for k, v in data.items()
                      if hasattr(cls, k) and not k.startswith('_')}
        return cls(**valid_data)


@dataclass
class PipelineConfig:
    """Volledige pipelineconfiguratie."""
    
    # Systeeminstellingen
    system: SystemConfig = field(default_factory=SystemConfig)

    # Invoer/Uitvoer
    step_file: str = ""
    pdf_file: Optional[str] = None
    output_dir: str = "."

    # Materiaal en hoeveelheid (voor kostprijs)
    material: str = "steel_s235"
    quantity: int = 1
    surface_treatment: Optional[str] = None

    # Module-instellingen
    modules: ModuleConfig = field(default_factory=ModuleConfig)

    # Tariefconfiguratie
    hourly_rates: PricingConfig = field(default_factory=PricingConfig)
    material_prices: MaterialPricesConfig = field(default_factory=MaterialPricesConfig)

    # Kostenkolommen voor eenvoudig rapport
    cost_columns: CostColumnsConfig = field(default_factory=CostColumnsConfig)

    # Cache-instellingen
    use_cache: bool = True
    cache_dir: str = ".pipeline_cache"
    from_stage: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        return result

    def save(self, filepath: str):
        """Sla configuratie op naar JSON-bestand."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "PipelineConfig":
        """Laad configuratie uit JSON-bestand."""
        with open(filepath, 'r') as f:
            data = json.load(f)

        # Haal geneste configs op
        system_data = data.pop('system', {})
        modules_data = data.pop('modules', {})
        hourly_rates_data = data.pop('hourly_rates', {})
        material_prices_data = data.pop('material_prices', {})
        cost_columns_data = data.pop('cost_columns', {})

        # Filter commentaar-sleutels uit hoofdconfig
        filtered_data = {k: v for k, v in data.items()
                         if not k.startswith('_') and hasattr(cls, k)}

        config = cls(**filtered_data)
        config.system = SystemConfig.from_dict(system_data)
        config.modules = ModuleConfig.from_dict(modules_data)
        config.hourly_rates = PricingConfig.from_dict(hourly_rates_data)
        config.material_prices = MaterialPricesConfig.from_dict(material_prices_data)
        config.cost_columns = CostColumnsConfig.from_dict(cost_columns_data)
        return config


# Modulegroepen voor eenvoudig aan/uit zetten
MODULE_GROUPS = {
    "basic": ["geometry", "topology", "holes", "faces"],
    "iso": ["iso2768_tolerances", "iso286_fits", "iso68_threads", "iso1302_surface", "iso13715_edges"],
    "manufacturing": ["mass_estimation", "component_classification", "detailed_parts"],
    "werkvoorbereiding": ["cost_estimation", "tool_list", "outsourcing", "surface_treatment", "purchase_spec"],
    "plaatwerk": ["sheetmetal_analysis", "bend_detection", "kantbank_tooling", "flat_pattern"],
    "all": None,  # Speciaal: alle modules
}


# Leesbare modulenamen (NL/EN)
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
    """Maak standaardconfiguratie met alle modules ingeschakeld."""
    return PipelineConfig(step_file=step_file)


def create_minimal_config(step_file: str = "") -> PipelineConfig:
    """Maak minimale configuratie (alleen basisanalyse)."""
    config = PipelineConfig(step_file=step_file)
    # Schakel geavanceerde modules uit
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
    Pas module-toggles voor aan/uit toe.

    Args:
        config: ModuleConfig om te wijzigen
        enable: Lijst met modulenamen of -groepen om in te schakelen
        disable: Lijst met modulenamen of -groepen om uit te schakelen
    """
    enable = enable or []
    disable = disable or []

    def resolve_modules(names: list) -> list:
        """Los groepsnamen op naar individuele modules."""
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

    # Pas eerst inschakelen toe, daarna uitschakelen
    for module in resolve_modules(enable):
        if hasattr(config, module):
            setattr(config, module, True)

    for module in resolve_modules(disable):
        if hasattr(config, module):
            setattr(config, module, False)

    return config


def print_module_status(config: ModuleConfig):
    """Print huidige modulestatus naar de console."""
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
