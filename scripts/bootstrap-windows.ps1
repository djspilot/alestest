param(
    [switch]$DoctorOnly,
    [switch]$SkipSystemDeps,
    [switch]$SkipPythonDeps,
    [switch]$SkipViewer,
    [switch]$SkipFreeCAD,
    [switch]$ForceReinstall,
    [switch]$ForceFreeCADReinstall,
    [string]$VenvPath = ".venv"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-CommandAvailable {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $combined = @($machinePath, $userPath) -join ";"
    if (-not [string]::IsNullOrWhiteSpace($combined)) {
        $env:Path = $combined
    }
}

function Test-IsWindowsPlatform {
    if (($PSVersionTable.PSVersion.Major -ge 6) -and $IsWindows) {
        return $true
    }

    return $env:OS -eq "Windows_NT"
}

function Get-SystemInstaller {
    if (Test-CommandAvailable "winget") {
        return "winget"
    }
    if (Test-CommandAvailable "choco") {
        return "choco"
    }
    throw "Geen ondersteunde Windows package manager gevonden. Installeer winget of Chocolatey."
}

function Install-SystemPackage {
    param(
        [string]$Installer,
        [string]$Label
    )

    switch ($Installer) {
        "winget" {
            $ids = @{
                python = "Python.Python.3.11"
                node = "OpenJS.NodeJS.LTS"
                git = "Git.Git"
            }
            $packageId = $ids[$Label]
            if (-not $packageId) {
                throw "Onbekend winget pakketlabel: $Label"
            }
            & winget install --id $packageId -e --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) {
                throw "winget installatie gefaald voor $Label"
            }
        }
        "choco" {
            $names = @{
                python = "python"
                node = "nodejs-lts"
                git = "git"
            }
            $packageName = $names[$Label]
            if (-not $packageName) {
                throw "Onbekend Chocolatey pakketlabel: $Label"
            }
            & choco install $packageName -y
            if ($LASTEXITCODE -ne 0) {
                throw "Chocolatey installatie gefaald voor $Label"
            }
        }
        default {
            throw "Niet-ondersteunde installer: $Installer"
        }
    }

    Refresh-ProcessPath
}

function Resolve-PythonLaunch {
    if (Test-CommandAvailable "py") {
        return @{
            Command = "py"
            Arguments = @("-3")
        }
    }
    if (Test-CommandAvailable "python") {
        return @{
            Command = "python"
            Arguments = @()
        }
    }
    return $null
}

function Resolve-NpmCommand {
    if (Test-CommandAvailable "npm") {
        return "npm"
    }
    if (Test-CommandAvailable "npm.cmd") {
        return "npm.cmd"
    }
    return $null
}

function Ensure-SystemTool {
    param(
        [string]$Label,
        [scriptblock]$Probe
    )

    if (& $Probe) {
        return
    }

    if ($SkipSystemDeps) {
        throw "$Label ontbreekt en -SkipSystemDeps is gezet."
    }

    $installer = Get-SystemInstaller
    Write-Step "Installeer $Label via $installer"
    Install-SystemPackage -Installer $installer -Label $Label

    if (-not (& $Probe)) {
        throw "$Label is nog steeds niet beschikbaar na installatie. Open een nieuw shell-venster en probeer opnieuw."
    }
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

function Invoke-Python {
    param(
        [string]$PythonCommand,
        [string[]]$PythonArgs,
        [string[]]$Arguments
    )
    & $PythonCommand @PythonArgs @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python commando gefaald: $PythonCommand $($PythonArgs + $Arguments -join ' ')"
    }
}

function Remove-IfExists {
    param([string]$Path)
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Set-FreeCADEnvironmentFromDoctor {
    param(
        [string]$PythonExe
    )

    $doctorJson = & $PythonExe -m manufacturing_pipeline.tools.ensure_unfold_runtime --doctor --json
    if ($LASTEXITCODE -ne 0) {
        throw "FreeCAD doctor commando gefaald."
    }

    $doctor = $doctorJson | ConvertFrom-Json
    $configured = $null
    if ($null -ne $doctor.PSObject.Properties['configured']) {
        $configured = $doctor.configured
    }
    elseif ($null -ne $doctor.PSObject.Properties['configured_runtime']) {
        $configured = $doctor.configured_runtime
    }
    if (-not $configured) {
        return
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

    $runtimeBinPaths = @(
        (Join-Path $configured.runtime_root "Library\bin"),
        (Join-Path $configured.runtime_root "Library\mingw-w64\bin"),
        (Join-Path $configured.runtime_root "bin")
    ) | Where-Object { $_ -and (Test-Path $_) }

    foreach ($runtimeBin in ($runtimeBinPaths | Select-Object -Unique)) {
        if ($env:Path -notlike "*$runtimeBin*") {
            $env:Path = "$runtimeBin;$env:Path"
        }
    }

    Write-Host "  FreeCAD runtime ingesteld:" -ForegroundColor Green
    Write-Host "    FREECAD_CMD=$($env:FREECAD_CMD)"
    Write-Host "    FREECAD_PYTHON=$($env:FREECAD_PYTHON)"
}

Push-Location $RepoRoot
try {
    if (-not (Test-IsWindowsPlatform)) {
        throw "Dit script is alleen bedoeld voor Windows."
    }

    Ensure-SystemTool -Label "python" -Probe { $null -ne (Resolve-PythonLaunch) }
    Ensure-SystemTool -Label "node" -Probe { $null -ne (Resolve-NpmCommand) }
    Ensure-SystemTool -Label "git" -Probe { Test-CommandAvailable "git" }

    $pythonLaunch = Resolve-PythonLaunch
    if (-not $pythonLaunch) {
        throw "Python is niet beschikbaar."
    }

    $npmCommand = Resolve-NpmCommand
    if (-not $npmCommand) {
        throw "npm is niet beschikbaar."
    }

    $venvRoot = Join-Path $RepoRoot $VenvPath
    $venvPython = Join-Path $venvRoot "Scripts\python.exe"
    $runtimeRoot = Join-Path $RepoRoot ".runtime\freecad"
    $runtimeMetadata = Join-Path $RepoRoot ".runtime\freecad_runtime.json"

    if (-not $DoctorOnly) {
        if ($ForceReinstall) {
            Write-Step "Verwijder bestaande lokale bootstrap artefacts"
            Remove-IfExists -Path $venvRoot
            Remove-IfExists -Path $runtimeRoot
            if (Test-Path $runtimeMetadata) {
                Remove-Item -LiteralPath $runtimeMetadata -Force
            }
        }

        if (-not (Test-Path $venvPython)) {
            Write-Step "Maak virtuele omgeving aan in $VenvPath"
            Invoke-Python -PythonCommand $pythonLaunch.Command -PythonArgs $pythonLaunch.Arguments -Arguments @("-m", "venv", $VenvPath)
        }

        Write-Step "Installeer Python requirements"
        Invoke-Checked -Command $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip")
        Invoke-Checked -Command $venvPython -Arguments @("-m", "pip", "install", "-r", "requirements.txt")

        if (-not $SkipPythonDeps) {
            Write-Step "Controleer host Python dependencies"
            Invoke-Checked -Command $venvPython -Arguments @("-m", "manufacturing_pipeline.tools.ensure_python_deps")
        }

        if (-not $SkipFreeCAD) {
            Write-Step "Controleer of installeer de headless FreeCAD runtime"
            $env:FREECAD_BOOTSTRAP_PACKAGE_MANAGER = "1"

            # Ensure micromamba is on PATH if it was installed to %LOCALAPPDATA%
            $micromambaDir = Join-Path $env:LOCALAPPDATA "micromamba"
            if ((Test-Path (Join-Path $micromambaDir "micromamba.exe")) -and ($micromambaDir -notin ($env:Path -split ";"))) {
                $env:Path = "$micromambaDir;$env:Path"
            }

            $freecadArgs = @("-m", "manufacturing_pipeline.tools.ensure_unfold_runtime")
            if ($ForceReinstall -or $ForceFreeCADReinstall) {
                $freecadArgs += "--force-reinstall"
            }
            Invoke-Checked -Command $venvPython -Arguments $freecadArgs
            Set-FreeCADEnvironmentFromDoctor -PythonExe $venvPython
        }

        if (-not $SkipViewer) {
            Write-Step "Installeer viewer Node dependencies (incl. vite)"
            Push-Location (Join-Path $RepoRoot "viewer")
            try {
                $npmInstallSucceeded = $true
                try {
                    Invoke-Checked -Command $npmCommand -Arguments @("install")
                }
                catch {
                    $npmInstallSucceeded = $false
                    Write-Host "  npm install faalde, opnieuw met --legacy-peer-deps..." -ForegroundColor Yellow
                }
                if (-not $npmInstallSucceeded) {
                    Invoke-Checked -Command $npmCommand -Arguments @("install", "--legacy-peer-deps")
                }

                # Verify vite command is executable
                $viteVersion = & $npmCommand "exec" "--" "vite" "--version" 2>&1
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "  vite check faalde, opnieuw met --legacy-peer-deps..." -ForegroundColor Yellow
                    Invoke-Checked -Command $npmCommand -Arguments @("install", "--legacy-peer-deps")
                    $viteVersion = & $npmCommand "exec" "--" "vite" "--version" 2>&1
                    if ($LASTEXITCODE -ne 0) {
                        throw "vite niet uitvoerbaar na npm install: $viteVersion"
                    }
                }
                Write-Host "  vite geinstalleerd ($viteVersion)" -ForegroundColor Green
            }
            finally {
                Pop-Location
            }
        }
    }

    Write-Step "Doctor output"
    if (Test-Path $venvPython) {
        Invoke-Checked -Command $venvPython -Arguments @("-m", "manufacturing_pipeline.tools.ensure_python_deps", "--doctor")
        if (-not $SkipFreeCAD) {
            $env:FREECAD_BOOTSTRAP_PACKAGE_MANAGER = "1"
            Invoke-Checked -Command $venvPython -Arguments @("-m", "manufacturing_pipeline.tools.ensure_unfold_runtime", "--doctor")
            Set-FreeCADEnvironmentFromDoctor -PythonExe $venvPython
        }
        Invoke-Checked -Command $venvPython -Arguments @("--version")
    }
    else {
        Invoke-Python -PythonCommand $pythonLaunch.Command -PythonArgs $pythonLaunch.Arguments -Arguments @("-m", "manufacturing_pipeline.tools.ensure_python_deps", "--doctor")
        if (-not $SkipFreeCAD) {
            $env:FREECAD_BOOTSTRAP_PACKAGE_MANAGER = "1"
            Invoke-Python -PythonCommand $pythonLaunch.Command -PythonArgs $pythonLaunch.Arguments -Arguments @("-m", "manufacturing_pipeline.tools.ensure_unfold_runtime", "--doctor")
        }
        Invoke-Python -PythonCommand $pythonLaunch.Command -PythonArgs $pythonLaunch.Arguments -Arguments @("--version")
    }
    Invoke-Checked -Command $npmCommand -Arguments @("--version")
    Invoke-Checked -Command "git" -Arguments @("--version")

    # Verify vite is available for the viewer
    if (-not $SkipViewer) {
        Push-Location (Join-Path $RepoRoot "viewer")
        try {
            Write-Host "  vite check:" -ForegroundColor Cyan
            $viteVersion = & $npmCommand "exec" "--" "vite" "--version" 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "vite check gefaald: $viteVersion"
            }
            Write-Host "  $viteVersion"
        }
        finally {
            Pop-Location
        }
    }
}
finally {
    Pop-Location
}
