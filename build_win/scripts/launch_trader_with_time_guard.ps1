[CmdletBinding()]
param(
    [string]$NtpServer = "time.windows.com",
    [int]$Samples = 5,
    [double]$ThresholdSeconds = 0.05,
    [int]$StableRoundsRequired = 3,
    [int]$MaxRepairCycles = 5,
    [int]$RoundSleepSeconds = 3,
    [string]$ProjectRoot = "C:\Jarvis\15_bonus\01_littile-bao",
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

function Invoke-StripchartMedian {
    param(
        [string]$Server,
        [int]$Count
    )

    $output = & w32tm /stripchart "/computer:$Server" "/samples:$Count" /dataonly 2>&1
    $exitCode = $LASTEXITCODE
    $lines = @($output | ForEach-Object { "$_" })
    if ($exitCode -ne 0) {
        throw "w32tm /stripchart failed with exit code $exitCode"
    }

    $offsets = @(Parse-StripchartOffsets -Lines $lines)
    if ($offsets.Count -eq 0) {
        throw "No stripchart offsets parsed."
    }

    return [pscustomobject]@{
        MedianSeconds = Get-Median -Values $offsets
        Offsets = $offsets
        Text = ($lines -join [Environment]::NewLine)
    }
}

function Invoke-RepairCycle {
    param(
        [string]$FixScriptPath,
        [string]$Server,
        [int]$Count,
        [double]$StepThresholdSeconds,
        [string]$LogPath
    )

    $repairArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $FixScriptPath,
        "-NtpServer", $Server,
        "-Samples", "$Count",
        "-LogPath", $LogPath,
        "-StepThresholdSeconds", "$StepThresholdSeconds",
        "-ForceStepCorrection"
    )

    & powershell.exe @repairArgs
    if ($LASTEXITCODE -ne 0) {
        throw "fix_windows_time_sync.ps1 exited with code $LASTEXITCODE"
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
        "-ThresholdSeconds", "$ThresholdSeconds",
        "-StableRoundsRequired", "$StableRoundsRequired",
        "-MaxRepairCycles", "$MaxRepairCycles",
        "-RoundSleepSeconds", "$RoundSleepSeconds",
        "-ProjectRoot", $ProjectRoot,
        "-Elevated"
    )

    $proc = Start-Process PowerShell -Verb RunAs -Wait -PassThru -ArgumentList (ConvertTo-ArgumentList -Items $argList)
    exit $proc.ExitCode
}

$distDir = Join-Path $ProjectRoot "build_win\dist"
$exePath = Join-Path $distDir "StockTrader-final.exe"
$fixScriptPath = Join-Path $PSScriptRoot "fix_windows_time_sync.ps1"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$guardLogPath = Join-Path $ProjectRoot "windows_time_guard_$stamp.log"

if (-not (Test-Path $exePath)) {
    throw "Missing trader executable: $exePath"
}
if (-not (Test-Path $fixScriptPath)) {
    throw "Missing fix script: $fixScriptPath"
}

Start-Transcript -Path $guardLogPath -Force | Out-Null

try {
    Write-Host "Trader launch guard started at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    Write-Host "Executable: $exePath"
    Write-Host "NTP server: $NtpServer"
    Write-Host "Threshold: $([math]::Round($ThresholdSeconds * 1000, 1)) ms"
    Write-Host "Stable rounds required: $StableRoundsRequired"
    Write-Host "Max repair cycles: $MaxRepairCycles"

    $healthy = $false
    for ($cycle = 1; $cycle -le $MaxRepairCycles; $cycle++) {
        Write-Host ""
        Write-Host "=== Repair cycle $cycle/$MaxRepairCycles ==="
        $repairLogPath = Join-Path $ProjectRoot "windows_time_sync_repair_prelaunch_$cycle`_$stamp.log"
        Invoke-RepairCycle `
            -FixScriptPath $fixScriptPath `
            -Server $NtpServer `
            -Count $Samples `
            -StepThresholdSeconds $ThresholdSeconds `
            -LogPath $repairLogPath

        $stableRounds = 0
        for ($round = 1; $round -le $StableRoundsRequired; $round++) {
            $measure = Invoke-StripchartMedian -Server $NtpServer -Count $Samples
            $medianMs = [math]::Round($measure.MedianSeconds * 1000, 1)
            Write-Host ("Validation round {0}/{1}: median offset {2} ms" -f $round, $StableRoundsRequired, $medianMs)

            if ([Math]::Abs($measure.MedianSeconds) -le $ThresholdSeconds) {
                $stableRounds += 1
            }
            else {
                $stableRounds = 0
                Write-Warning ("Offset exceeded threshold during validation: {0} ms" -f $medianMs)
                break
            }

            if ($round -lt $StableRoundsRequired) {
                Start-Sleep -Seconds $RoundSleepSeconds
            }
        }

        if ($stableRounds -ge $StableRoundsRequired) {
            $healthy = $true
            Write-Host ""
            Write-Host "Time guard passed. Launching trader..."
            Start-Process -FilePath $exePath -WorkingDirectory $distDir | Out-Null
            break
        }

        if ($cycle -lt $MaxRepairCycles) {
            Write-Host "Validation failed. Waiting before next repair cycle..."
            Start-Sleep -Seconds ([Math]::Max(3, $RoundSleepSeconds))
        }
    }

    if (-not $healthy) {
        throw "Unable to reach stable clock state after $MaxRepairCycles repair cycles."
    }
}
finally {
    Stop-Transcript | Out-Null
    Write-Host ""
    Write-Host "Guard log: $guardLogPath"
}
