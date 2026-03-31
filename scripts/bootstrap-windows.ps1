param(
    [switch]$DoctorOnly,
    [switch]$SkipSystemDeps,
    [switch]$SkipPythonDeps,
    [switch]$SkipViewer,
    [switch]$SkipFreeCAD,
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

    if (-not $DoctorOnly) {
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

            Invoke-Checked -Command $venvPython -Arguments @("-m", "manufacturing_pipeline.tools.ensure_unfold_runtime")
        }

        if (-not $SkipViewer) {
            Write-Step "Installeer viewer Node dependencies (incl. vite)"
            Push-Location (Join-Path $RepoRoot "viewer")
            try {
                Invoke-Checked -Command $npmCommand -Arguments @("install")
                # Verify vite is available via npx
                $viteCheck = & $npmCommand "list" "vite" 2>&1
                if ($LASTEXITCODE -ne 0 -or ($viteCheck -notmatch "vite")) {
                    Write-Host "  vite niet gevonden na npm install, opnieuw proberen..." -ForegroundColor Yellow
                    Invoke-Checked -Command $npmCommand -Arguments @("install", "--legacy-peer-deps")
                }
                Write-Host "  vite geinstalleerd" -ForegroundColor Green
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
            Invoke-Checked -Command $npmCommand -Arguments @("list", "vite")
        }
        finally {
            Pop-Location
        }
    }
}
finally {
    Pop-Location
}
