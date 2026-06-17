[CmdletBinding()]
param(
    [string]$NtpServer = "time.windows.com",
    [int]$Samples = 5
)

$ErrorActionPreference = "Stop"

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

if (-not (Test-IsAdministrator)) {
    Write-Error "Please run this script from Administrator PowerShell."
    exit 1
}

Write-Host "Windows time sync repair started at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
Write-Host "Using NTP server: $NtpServer"

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
Invoke-W32tm -Arguments @("/config", "/manualpeerlist:$NtpServer", "/syncfromflags:manual", "/update")

Write-Host ""
Write-Host "Resync"
Invoke-W32tm -Arguments @("/resync", "/force")

Write-Host ""
Write-Host "Post-check"
Invoke-W32tm -Arguments @("/query", "/status")
Invoke-W32tm -Arguments @("/stripchart", "/computer:$NtpServer", "/samples:$Samples", "/dataonly")

Write-Host ""
Write-Host "Windows time sync repair completed."
