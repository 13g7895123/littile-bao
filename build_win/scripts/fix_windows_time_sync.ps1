[CmdletBinding()]
param(
    [string]$NtpServer = "time.windows.com",
    [int]$Samples = 5,
    [int]$MaxResyncAttempts = 3,
    [string]$LogPath = "",
    [switch]$ForceStepCorrection,
    [double]$StepThresholdSeconds = 0.05
)

$ErrorActionPreference = "Stop"

if (-not $LogPath) {
    $LogPath = Join-Path $PSScriptRoot "fix_windows_time_sync.last.log"
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-W32tm {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host ""
    Write-Host ("> w32tm " + ($Arguments -join " "))
    & w32tm @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "w32tm failed with exit code $exitCode"
    }
}

function Restart-W32TimeService {
    Write-Host ""
    Write-Host "Restarting W32Time service"
    $service = Get-Service W32Time -ErrorAction Stop
    if ($service.Status -eq "Running") {
        Stop-Service W32Time -Force
        $service.WaitForStatus("Stopped", [TimeSpan]::FromSeconds(15))
    }
    Start-Service W32Time
    $service.WaitForStatus("Running", [TimeSpan]::FromSeconds(15))
    Get-Service W32Time | Format-List Name, Status, StartType
}

function Invoke-ResyncWithRetry {
    param(
        [int]$Attempts
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        Write-Host ""
        Write-Host "Resync attempt $attempt/$Attempts"
        try {
            Invoke-W32tm -Arguments @("/resync", "/rediscover")
            Start-Sleep -Seconds 3
            return
        }
        catch {
            if ($attempt -ge $Attempts) {
                throw
            }
            Write-Warning "Resync attempt $attempt failed: $($_.Exception.Message)"
            Start-Sleep -Seconds 2
        }
    }
}

function Measure-TimeOffsetSeconds {
    param(
        [string]$Server,
        [int]$Count
    )

    Write-Host ""
    Write-Host "> w32tm /stripchart /computer:$Server /samples:$Count /dataonly"
    $output = & w32tm /stripchart "/computer:$Server" "/samples:$Count" /dataonly
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) {
        throw "w32tm stripchart failed with exit code $exitCode"
    }

    $offsets = @()
    foreach ($line in $output) {
        if ($line -match "([-+]\d+\.\d+)s") {
            $offsets += [double]$Matches[1]
        }
    }
    if ($offsets.Count -eq 0) {
        throw "No stripchart offsets parsed."
    }

    $sorted = $offsets | Sort-Object
    $mid = [int][Math]::Floor($sorted.Count / 2)
    if (($sorted.Count % 2) -eq 1) {
        return $sorted[$mid]
    }
    return ($sorted[$mid - 1] + $sorted[$mid]) / 2.0
}

function Invoke-StepCorrection {
    param(
        [string]$Server,
        [int]$Count,
        [double]$ThresholdSeconds
    )

    $offset = Measure-TimeOffsetSeconds -Server $Server -Count $Count
    Write-Host ""
    Write-Host ("Measured median offset: {0:N6}s" -f $offset)
    if ([Math]::Abs($offset) -lt $ThresholdSeconds) {
        Write-Host ("Offset is below step threshold {0:N3}s; skipping direct Set-Date correction." -f $ThresholdSeconds)
        return
    }

    $before = Get-Date
    $primaryTarget = $before.AddSeconds(-$offset)
    Write-Host ("Primary Set-Date correction: {0:O} -> {1:O}" -f $before, $primaryTarget)
    Set-Date -Date $primaryTarget | Out-Host
    Start-Sleep -Seconds 2

    $postPrimary = Measure-TimeOffsetSeconds -Server $Server -Count $Count
    Write-Host ("Post-primary median offset: {0:N6}s" -f $postPrimary)
    if ([Math]::Abs($postPrimary) -le [Math]::Abs($offset)) {
        Write-Host "Primary correction improved offset."
        return
    }

    Write-Warning ("Primary correction worsened offset ({0:N6}s -> {1:N6}s); trying opposite direction." -f $offset, $postPrimary)
    $fallbackTarget = $before.AddSeconds($offset)
    Write-Host ("Fallback Set-Date correction: {0:O} -> {1:O}" -f (Get-Date), $fallbackTarget)
    Set-Date -Date $fallbackTarget | Out-Host
    Start-Sleep -Seconds 2

    $postFallback = Measure-TimeOffsetSeconds -Server $Server -Count $Count
    Write-Host ("Post-fallback median offset: {0:N6}s" -f $postFallback)
}

if (-not (Test-IsAdministrator)) {
    Write-Error "Please run this script from Administrator PowerShell."
    Write-Host ""
    Write-Host "Current shell is not elevated enough to repair Windows time."
    Write-Host "If you started from WSL, use build_win/scripts/fix_windows_time_sync.sh to trigger an elevated PowerShell window."
    exit 1
}

Start-Transcript -Path $LogPath -Force | Out-Null

Write-Host "Windows time sync repair started at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
Write-Host "Using NTP server: $NtpServer"
Write-Host "Log path: $LogPath"
Write-Host "Force step correction: $ForceStepCorrection"

Write-Host ""
Write-Host "Pre-check"
Invoke-W32tm -Arguments @("/query", "/status")
Invoke-W32tm -Arguments @("/stripchart", "/computer:$NtpServer", "/samples:$Samples", "/dataonly")

Write-Host ""
Write-Host "Ensuring W32Time service is running"
$service = Get-Service W32Time -ErrorAction Stop
if ($service.Status -ne "Running") {
    Start-Service W32Time
    $service.WaitForStatus("Running", [TimeSpan]::FromSeconds(10))
}
Get-Service W32Time | Format-List Name, Status, StartType

Write-Host ""
Write-Host "Configuring manual peer list"
$peerList = "$NtpServer,0x8 time.google.com,0x8 pool.ntp.org,0x8"
Invoke-W32tm -Arguments @("/config", "/manualpeerlist:$peerList", "/syncfromflags:manual", "/reliable:no", "/update")

Write-Host ""
Restart-W32TimeService

Write-Host ""
Write-Host "Resync"
Invoke-ResyncWithRetry -Attempts $MaxResyncAttempts

if ($ForceStepCorrection) {
    Write-Host ""
    Write-Host "Force step correction"
    Invoke-StepCorrection -Server $NtpServer -Count $Samples -ThresholdSeconds $StepThresholdSeconds

    Write-Host ""
    Write-Host "Final resync after step correction"
    Invoke-ResyncWithRetry -Attempts $MaxResyncAttempts
}

Write-Host ""
Write-Host "Post-check"
Invoke-W32tm -Arguments @("/query", "/peers")
Invoke-W32tm -Arguments @("/query", "/status")
Measure-TimeOffsetSeconds -Server $NtpServer -Count $Samples | ForEach-Object {
    Write-Host ("Post-check median offset: {0:N6}s" -f $_)
}

Write-Host ""
Write-Host "Windows time sync repair completed."
Stop-Transcript | Out-Null
