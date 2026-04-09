param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"

$AppRoot = Split-Path -Parent $PSScriptRoot
$ProjectRoot = Split-Path -Parent $AppRoot
Set-Location $AppRoot

function Add-EnvPath {
    param(
        [string]$Name,
        [string[]]$Paths
    )

    $existing = [Environment]::GetEnvironmentVariable($Name, "Process")
    $parts = @()

    foreach ($path in $Paths) {
        if (-not [string]::IsNullOrWhiteSpace($path) -and (Test-Path $path)) {
            $parts += $path
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($existing)) {
        $parts += $existing
    }

    if ($parts.Count -gt 0) {
        [Environment]::SetEnvironmentVariable(
            $Name,
            ($parts -join [IO.Path]::PathSeparator),
            "Process"
        )
    }
}

Add-EnvPath -Name "PYTHONPATH" -Paths @(
    $ProjectRoot,
    $AppRoot,
    (Join-Path $AppRoot "ten_packages\system\ten_runtime_python\lib"),
    (Join-Path $AppRoot "ten_packages\system\ten_runtime_python\interface"),
    (Join-Path $AppRoot "ten_packages\system\ten_ai_base\interface"),
    (Join-Path $AppRoot "ten_packages\system")
)

Add-EnvPath -Name "NODE_PATH" -Paths @(
    (Join-Path $AppRoot "ten_packages\system\ten_runtime_nodejs\lib")
)

Add-EnvPath -Name "PATH" -Paths @(
    (Join-Path $AppRoot "ten_packages\system\ten_runtime_go\lib"),
    (Join-Path $AppRoot "ten_packages\system\ten_runtime\lib"),
    (Join-Path $AppRoot "ten_packages\extension\agora_rtc\lib")
)

$MainExe = Join-Path $AppRoot "bin\main.exe"
if (-not (Test-Path $MainExe)) {
    Write-Host "[ERROR] $MainExe not found." -ForegroundColor Red
    Write-Host "Run 'tman install' in $AppRoot first, then retry 'tman run start'." -ForegroundColor Yellow
    exit 1
}

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "  AI-HR TEN app starting" -ForegroundColor Green
Write-Host "  App root: $AppRoot"
Write-Host "  Project root: $ProjectRoot"
Write-Host "  Main exe: $MainExe"
Write-Host "===============================================" -ForegroundColor Cyan

& $MainExe @ExtraArgs
$exitCode = $LASTEXITCODE
if ($null -eq $exitCode) {
    $exitCode = 0
}
exit $exitCode
