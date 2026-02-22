#!/usr/bin/env bash
set -euo pipefail

echo "== Devcontainer venv debug: $(date) ==="

echo "-- Python versions --"
command -v python3 >/dev/null 2>&1 && python3 --version || echo "python3: not found"
command -v python >/dev/null 2>&1 && python --version || echo "python: not found"

echo "-- Which pythons --"
which python3 || true
which python || true

echo "-- /opt/venv --"
if [ -d "/opt/venv" ]; then
  ls -la /opt/venv | sed -n '1,200p'
  /opt/venv/bin/python -m pip --version || echo "/opt/venv pip: not available"
else
  echo "/opt/venv not present"
fi

echo "-- workspace .venv (/workspaces/go2rtc-shared-cam/.venv) --"
if [ -d "/workspaces/go2rtc-shared-cam/.venv" ]; then
  ls -la /workspaces/go2rtc-shared-cam/.venv | sed -n '1,200p'
  if [ -x "/workspaces/go2rtc-shared-cam/.venv/bin/python" ]; then
    /workspaces/go2rtc-shared-cam/.venv/bin/python -m pip --version || echo "workspace venv pip: not available"
  else
    echo "workspace venv python not executable or missing"
  fi
else
  echo "workspace .venv not present"
fi

echo "-- Mounted filesystem info (relevant mounts) --"
mount | grep workspaces || true

echo "-- pip config (system/user) --"
command -v pip3 >/dev/null 2>&1 && pip3 config list || echo "pip3 not found"

echo "-- End debug --"
