<#
.SYNOPSIS
  One-click L6 live trend runner for OtakuNeko.

.DESCRIPTION
  Modes:
    smoke     one cheap live case (agent + Judge) to verify connectivity
    baseline  repeated run, writes/updates the trend baseline
    compare   repeated run, compares against the committed baseline

  Credentials come from the backend/.env application settings (or the process
  environment). This script never accepts or prints an API key.

.EXAMPLE
  .\scripts\l6-trend.ps1
  .\scripts\l6-trend.ps1 -Mode baseline -Repeats 3
  .\scripts\l6-trend.ps1 -Mode compare
  .\scripts\l6-trend.ps1 -Mode smoke -Model deepseek-flash
#>
param(
    [ValidateSet("smoke", "baseline", "compare")]
    [string]$Mode = "smoke",

    [int]$Repeats = 3,

    [string]$Model = "deepseek-flash",

    [string]$BaseUrl = "https://api.deepseek.com",

    [string]$Config = "evals/config/real-model-quality.yaml",

    [string[]]$Case = @(),

    [switch]$Force
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv is not installed or not on PATH."
    exit 2
}

$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$Slug = ($Model -replace "[^A-Za-z0-9._-]", "_")
$Baseline = "evals/baselines/l6-trend-$Slug.json"
$RunId = "$Mode-$Stamp"
$EffectiveRepeats = if ($Mode -eq "smoke") { 1 } else { $Repeats }

$TrendArgs = @(
    "--directory", "backend", "python", "-m", "app.evaluation.trend",
    "--config", $Config,
    "--model", $Model,
    "--base-url", $BaseUrl,
    "--run-id", $RunId
)

if ($Mode -eq "smoke" -and $Case.Count -eq 0) {
    $Case = @("real-model-chat-basic")
}
$TrendArgs += @("--repeats", "$EffectiveRepeats")

foreach ($Item in $Case) {
    $TrendArgs += @("--case", $Item)
}

if ($Mode -eq "baseline") {
    if ((Test-Path $Baseline) -and -not $Force) {
        Write-Host "Baseline already exists: $Baseline" -ForegroundColor Yellow
        Write-Host "Re-run with -Force only after reviewing the old baseline." -ForegroundColor Yellow
        exit 2
    }
    $TrendArgs += @("--baseline", $Baseline, "--update-baseline")
    if ($Force) {
        $TrendArgs += "--force"
    }
} elseif ($Mode -eq "compare") {
    if (-not (Test-Path $Baseline)) {
        Write-Host "Baseline missing: $Baseline" -ForegroundColor Yellow
        Write-Host "Run -Mode baseline first, review it, then commit it." -ForegroundColor Yellow
        exit 2
    }
    $TrendArgs += @("--baseline", $Baseline)
}

Write-Host "L6 trend mode=$Mode model=$Model repeats=$EffectiveRepeats run=$RunId" -ForegroundColor Cyan
Write-Host "Baseline: $Baseline" -ForegroundColor Cyan
Write-Host "Reports: backend/.runtime/evaluation/l6-trend/$RunId/" -ForegroundColor Cyan
Write-Host ""

& uv run @TrendArgs
$Code = $LASTEXITCODE
Write-Host ""
Write-Host "Exit code: $Code" -ForegroundColor $(if ($Code -eq 0) { "Green" } else { "Red" })
exit $Code
