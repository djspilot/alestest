param(
    [string]$VenvPath = ".venv"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot "$VenvPath\Scripts\python.exe"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Checked {
    param(
        [string]$Command,
        [string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Commando gefaald: $Command $($Arguments -join ' ')"
    }
}

if (-not (Test-Path $VenvPython)) {
    throw "Python venv niet gevonden op $VenvPython. Run eerst .\scripts\bootstrap-windows.ps1"
}

Push-Location $RepoRoot
try {
    Write-Step "Host dependency doctor"
    Invoke-Checked -Command $VenvPython -Arguments @("-m", "manufacturing_pipeline.tools.ensure_python_deps", "--doctor")

    Write-Step "FreeCAD runtime doctor (JSON)"
    $doctorJson = & $VenvPython -m manufacturing_pipeline.tools.ensure_unfold_runtime --doctor --json
    if ($LASTEXITCODE -ne 0) {
        throw "ensure_unfold_runtime --doctor faalde"
    }
    $doctor = $doctorJson | ConvertFrom-Json
    $doctorJson

    $configured = $doctor.configured_runtime
    if (-not $configured) {
        throw "Geen configured_runtime ontvangen uit doctor-output"
    }

    foreach ($pair in @(
        @{ Name = "FREECAD_RUNTIME_ROOT"; Value = $configured.runtime_root },
        @{ Name = "FREECAD_PATH"; Value = $configured.freecad_path },
        @{ Name = "FREECAD_PYTHON"; Value = $configured.freecad_python },
        @{ Name = "FREECAD_CMD"; Value = $configured.freecad_cmd },
        @{ Name = "FREECAD_LIB"; Value = $configured.freecad_lib },
        @{ Name = "FREECAD_MOD"; Value = $configured.freecad_mod }
    )) {
        if (-not [string]::IsNullOrWhiteSpace($pair.Value)) {
            [Environment]::SetEnvironmentVariable($pair.Name, $pair.Value, "Process")
        }
    }

    Write-Step "Controleer runtime paden"
    foreach ($path in @(
        $env:FREECAD_RUNTIME_ROOT,
        $env:FREECAD_PYTHON,
        $env:FREECAD_CMD,
        $env:FREECAD_LIB,
        $env:FREECAD_MOD
    )) {
        if ([string]::IsNullOrWhiteSpace($path)) {
            Write-Host "MISSING: lege path" -ForegroundColor Yellow
            continue
        }
        if (Test-Path $path) {
            Write-Host "OK: $path" -ForegroundColor Green
        }
        else {
            Write-Host "MISSING: $path" -ForegroundColor Red
        }
    }

    Write-Step "Test FreeCAD imports in managed runtime"
    $importCode = @'
import json
import os
import sys

result = {
    "platform": sys.platform,
    "freecad_python": os.environ.get("FREECAD_PYTHON", ""),
    "freecad_cmd": os.environ.get("FREECAD_CMD", ""),
    "freecad_lib": os.environ.get("FREECAD_LIB", ""),
    "freecad_mod": os.environ.get("FREECAD_MOD", ""),
}

for key in ("FREECAD_LIB", "FREECAD_MOD"):
    value = os.environ.get(key, "")
    if value and os.path.isdir(value) and value not in sys.path:
        sys.path.insert(0, value)

class _MockSel:
    @staticmethod
    def getSelection():
        return []

class _MockGui:
    Selection = _MockSel()

sys.modules["FreeCADGui"] = _MockGui()

try:
    import FreeCAD
    import Part
    import SheetMetalUnfolder
    result["success"] = True
    result["freecad_version"] = getattr(FreeCAD, "Version", lambda: [])()
except Exception as exc:
    result["success"] = False
    result["error"] = str(exc)

print(json.dumps(result, indent=2))
'@
    Invoke-Checked -Command $env:FREECAD_PYTHON -Arguments @("-c", $importCode)

    Write-Step "Klaar"
    Write-Host "Als unfold nog faalt, stuur de volledige output van dit script plus de [runtime-failure] regels uit de app." -ForegroundColor Cyan
}
finally {
    Pop-Location
}
