param(
    [Parameter(Mandatory = $true)]
    [string]$Step,

    [string]$Reference = "",
    [string]$Output = "",
    [string]$Material = "steel_s235",
    [string]$Tag = "",
    [switch]$FailOnWarning
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$workspaceRoot = Split-Path -Parent $repoRoot

$pythonCandidates = @(
    (Join-Path $workspaceRoot ".venv\Scripts\python.exe"),
    (Join-Path $repoRoot ".venv\Scripts\python.exe")
)

$pythonExe = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $pythonExe) {
    $pythonExe = "python"
}

function Resolve-InputPath([string]$pathValue) {
    if ([string]::IsNullOrWhiteSpace($pathValue)) {
        return ""
    }
    if ([System.IO.Path]::IsPathRooted($pathValue)) {
        return (Resolve-Path -LiteralPath $pathValue).Path
    }

    $candidateWorkspace = Join-Path $workspaceRoot $pathValue
    if (Test-Path $candidateWorkspace) {
        return (Resolve-Path -LiteralPath $candidateWorkspace).Path
    }

    $candidateRepo = Join-Path $repoRoot $pathValue
    if (Test-Path $candidateRepo) {
        return (Resolve-Path -LiteralPath $candidateRepo).Path
    }

    throw "Path not found: $pathValue"
}

$stepPath = Resolve-InputPath $Step
if ([string]::IsNullOrWhiteSpace($stepPath)) {
    throw "STEP path is empty"
}

if ([string]::IsNullOrWhiteSpace($Output)) {
    $stepStem = [System.IO.Path]::GetFileNameWithoutExtension($stepPath)
    $stepDir = Split-Path -Parent $stepPath
    $outputPath = Join-Path $stepDir ("{0}_generated_latest.xml" -f $stepStem)
} elseif ([System.IO.Path]::IsPathRooted($Output)) {
    $outputPath = $Output
} else {
    $outputPath = Join-Path $workspaceRoot $Output
}

$referencePath = ""
if (-not [string]::IsNullOrWhiteSpace($Reference)) {
    $referencePath = Resolve-InputPath $Reference
}

Push-Location $repoRoot
try {
    Write-Host "=== STEP -> XML generation ==="
    Write-Host "Python:    $pythonExe"
    Write-Host "STEP:      $stepPath"
    Write-Host "Output XML:$outputPath"

    $generateArgs = @(
        "scripts/generate_xml_dxf.py",
        "--step", $stepPath,
        "--output", $outputPath,
        "--material", $Material,
        "--no-compare"
    )

    if ($referencePath) {
        $generateArgs += @("--reference", $referencePath)
        Write-Host "Reference: $referencePath"
    }

    & $pythonExe @generateArgs
    if ($LASTEXITCODE -ne 0) {
        throw "XML generation failed (exit code $LASTEXITCODE)"
    }

    Write-Host ""
    Write-Host "=== XML status guard + snapshot ==="
    $guardArgs = @(
        "scripts/preserve_xml_status.py",
        "--xml", $outputPath
    )

    if (-not [string]::IsNullOrWhiteSpace($Tag)) {
        $guardArgs += @("--tag", $Tag)
    }
    if ($FailOnWarning) {
        $guardArgs += "--fail-on-warning"
    }

    & $pythonExe @guardArgs
    if ($LASTEXITCODE -ne 0) {
        throw "XML status guard failed (exit code $LASTEXITCODE)"
    }

    Write-Host ""
    Write-Host "[OK] Pipeline complete. XML generated and snapshot stored in snapshots/xml_status."
}
finally {
    Pop-Location
}
