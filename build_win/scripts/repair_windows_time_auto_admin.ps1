[CmdletBinding()]
param(
    [string]$NtpServer = "time.windows.com",
    [int]$Samples = 5,
    [string]$OutputDir = "C:\Jarvis\15_bonus\01_littile-bao",
    [switch]$ForceStepCorrection = $true,
    [double]$StepThresholdSeconds = 0.05,
    [switch]$Elevated
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function ConvertTo-ArgumentList {
    param([string[]]$Items)

    $escaped = foreach ($item in $Items) {
        if ($null -eq $item) {
            '""'
            continue
        }
        '"' + ($item -replace '"', '\"') + '"'
    }
    return ($escaped -join " ")
}

function Parse-StripchartOffsets {
    param([string[]]$Lines)

    $offsets = @()
    foreach ($line in $Lines) {
        if ($line -match "([-+]\d+\.\d+)s") {
            $offsets += [double]$Matches[1]
        }
    }
    return $offsets
}

function Get-Median {
    param([double[]]$Values)

    if (-not $Values -or $Values.Count -eq 0) {
        throw "No values for median."
    }

    $sorted = $Values | Sort-Object
    $mid = [int][Math]::Floor($sorted.Count / 2)
    if (($sorted.Count % 2) -eq 1) {
        return $sorted[$mid]
    }
    return ($sorted[$mid - 1] + $sorted[$mid]) / 2.0
}

function Invoke-W32tmCapture {
    param([string[]]$Arguments)

    $output = & w32tm @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $lines = @($output | ForEach-Object { "$_" })
    return [pscustomobject]@{
        ExitCode = $exitCode
        Lines = $lines
        Text = ($lines -join [Environment]::NewLine)
    }
}

if (-not (Test-IsAdministrator)) {
    $scriptPath = $MyInvocation.MyCommand.Path
    if (-not $scriptPath) {
        throw "Unable to resolve current script path for elevation."
    }

    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $scriptPath,
        "-NtpServer", $NtpServer,
        "-Samples", "$Samples",
        "-OutputDir", $OutputDir,
        "-StepThresholdSeconds", "$StepThresholdSeconds",
        "-Elevated"
    )
    if ($ForceStepCorrection) {
        $argList += "-ForceStepCorrection"
    }

    $proc = Start-Process PowerShell -Verb RunAs -Wait -PassThru -ArgumentList (ConvertTo-ArgumentList -Items $argList)
    exit $proc.ExitCode
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$repoScript = Join-Path $PSScriptRoot "fix_windows_time_sync.ps1"
if (-not (Test-Path $repoScript)) {
    throw "Missing fix script: $repoScript"
}

$repairLogPath = Join-Path $OutputDir "windows_time_sync_repair_$stamp.log"
$summaryTxtPath = Join-Path $OutputDir "windows_time_sync_summary_latest.txt"
$summaryJsonPath = Join-Path $OutputDir "windows_time_sync_summary_latest.json"

$startAt = Get-Date
$repairSucceeded = $false
$repairError = $null

try {
    $repairArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $repoScript,
        "-NtpServer", $NtpServer,
        "-Samples", "$Samples",
        "-LogPath", $repairLogPath,
        "-StepThresholdSeconds", "$StepThresholdSeconds"
    )
    if ($ForceStepCorrection) {
        $repairArgs += "-ForceStepCorrection"
    }

    & powershell.exe @repairArgs
    if ($LASTEXITCODE -ne 0) {
        throw "fix_windows_time_sync.ps1 exited with code $LASTEXITCODE"
    }
    $repairSucceeded = $true
}
catch {
    $repairError = $_.Exception.Message
}

$status = Invoke-W32tmCapture -Arguments @("/query", "/status")
$peers = Invoke-W32tmCapture -Arguments @("/query", "/peers")
$strip = Invoke-W32tmCapture -Arguments @("/stripchart", "/computer:$NtpServer", "/samples:$Samples", "/dataonly")

$medianOffsetSeconds = $null
$offsets = @()
if ($strip.ExitCode -eq 0) {
    try {
        $offsets = @(Parse-StripchartOffsets -Lines $strip.Lines)
        if ($offsets.Count -gt 0) {
            $medianOffsetSeconds = Get-Median -Values $offsets
        }
    }
    catch {
    }
}

$endAt = Get-Date
$sourceLine = ($status.Lines | Where-Object { $_ -match "來源|Source" } | Select-Object -First 1)

$summary = [ordered]@{
    started_at = $startAt.ToString("o")
    completed_at = $endAt.ToString("o")
    ntp_server = $NtpServer
    samples = $Samples
    output_dir = $OutputDir
    repair_succeeded = $repairSucceeded
    repair_error = $repairError
    median_offset_seconds = $medianOffsetSeconds
    source_line = $sourceLine
    repair_log_path = $repairLogPath
    status_exit_code = $status.ExitCode
    stripchart_exit_code = $strip.ExitCode
    peers_exit_code = $peers.ExitCode
    stripchart_offsets = $offsets
}

$summaryText = @(
    "Windows Time Sync Summary"
    "Started: $($summary.started_at)"
    "Completed: $($summary.completed_at)"
    "NTP Server: $($summary.ntp_server)"
    "Samples: $($summary.samples)"
    "Repair Succeeded: $($summary.repair_succeeded)"
    "Repair Error: $($summary.repair_error)"
    "Median Offset Seconds: $($summary.median_offset_seconds)"
    "Source: $($summary.source_line)"
    "Repair Log: $($summary.repair_log_path)"
    ""
    "w32tm /query /status"
    $status.Text
    ""
    "w32tm /query /peers"
    $peers.Text
    ""
    "w32tm /stripchart"
    $strip.Text
)

$summaryText -join [Environment]::NewLine | Set-Content -Path $summaryTxtPath -Encoding UTF8
$summary | ConvertTo-Json -Depth 4 | Set-Content -Path $summaryJsonPath -Encoding UTF8

Write-Host ""
Write-Host "Time sync completed."
Write-Host "Summary: $summaryTxtPath"
Write-Host "JSON:    $summaryJsonPath"
Write-Host "Log:     $repairLogPath"
