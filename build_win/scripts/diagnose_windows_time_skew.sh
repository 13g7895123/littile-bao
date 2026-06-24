#!/usr/bin/env bash
set -euo pipefail

NTP_SERVER="${1:-time.windows.com}"
SAMPLES="${SAMPLES:-5}"

run_cmd() {
  local cmd="$1"
  cmd.exe /c "$cmd" 2>&1 | tr -d '\r'
}

run_ps() {
  local cmd="$1"
  powershell.exe -NoProfile -Command "$cmd" 2>&1 | tr -d '\r'
}

stripchart_output="$(run_cmd "w32tm /stripchart /computer:${NTP_SERVER} /samples:${SAMPLES} /dataonly" || true)"
status_output="$(run_cmd "w32tm /query /status" || true)"
service_output="$(run_ps "Get-Service W32Time | Format-List Name,Status,StartType" || true)"

mapfile -t offsets < <(printf '%s\n' "$stripchart_output" | grep -oE '[-+][0-9]+\.[0-9]+s' || true)
source_name="unknown"
if printf '%s\n' "$status_output" | grep -Fq 'Local CMOS Clock'; then
  source_name="Local CMOS Clock"
elif printf '%s\n' "$status_output" | grep -Fq 'time.windows.com'; then
  source_name="time.windows.com"
fi

permission_denied="no"
if printf '%s\n%s\n' "$stripchart_output" "$status_output" | grep -Fq '0x80070005'; then
  permission_denied="yes"
fi

echo "Windows Time Skew Diagnosis"
echo "NTP server: ${NTP_SERVER}"
echo "Samples: ${SAMPLES}"
echo "Source: ${source_name}"
echo "PermissionDenied: ${permission_denied}"
echo "Offsets:"
if [ "${#offsets[@]}" -eq 0 ]; then
  echo "  (none parsed)"
else
  printf '  %s\n' "${offsets[@]}"
fi
echo
echo "Raw stripchart:"
printf '%s\n' "$stripchart_output"
echo
echo "Raw status:"
printf '%s\n' "$status_output"
echo
echo "W32Time service:"
printf '%s\n' "$service_output"
