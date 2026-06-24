#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PS1_PATH="$SCRIPT_DIR/fix_windows_time_sync.ps1"
WIN_PS1_PATH="$(wslpath -w "$PS1_PATH")"
LOG_PATH="$SCRIPT_DIR/fix_windows_time_sync.last.log"
WIN_LOG_PATH="$(wslpath -w "$LOG_PATH")"

echo "Pre-check"
"$SCRIPT_DIR/diagnose_windows_time_skew.sh"
echo
echo "Requesting elevated PowerShell to repair Windows time"
powershell.exe -NoProfile -Command "\$p = Start-Process PowerShell -Verb RunAs -Wait -PassThru -ArgumentList '-ExecutionPolicy Bypass -File \"$WIN_PS1_PATH\" -LogPath \"$WIN_LOG_PATH\" -ForceStepCorrection'; exit \$p.ExitCode"
echo "Repair log: $LOG_PATH"
if [ -f "$LOG_PATH" ]; then
  echo
  echo "Last repair log tail"
  tail -n 80 "$LOG_PATH"
fi
