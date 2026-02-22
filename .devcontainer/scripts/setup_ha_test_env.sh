#!/usr/bin/env bash
set -euo pipefail

# Minimal devcontainer setup script — assumes the image provides a working, writable venv at /opt/venv
VENV="/opt/venv"
WORKSPACE_DIR="/workspaces/go2rtc-shared-cam"
WHEEL_DIR="/workspaces/.wheels"
PIP_CACHE_DIR="/workspaces/.cache/pip"

if [ ! -x "${VENV}/bin/python" ]; then
    echo "Error: expected venv at ${VENV} but python not found. Ensure the image provides /opt/venv"
    exit 1
fi

echo "Using venv: ${VENV}"
echo "Using wheel cache: ${WHEEL_DIR}"
sudo mkdir -p "${WHEEL_DIR}" "${PIP_CACHE_DIR}"
sudo chown -R "$(id -u):$(id -g)" "${WHEEL_DIR}" "${PIP_CACHE_DIR}"

VENV_PYTHON="${VENV}/bin/python"

echo "Updating pip and wheel..."
${VENV_PYTHON} -m pip install -U pip setuptools wheel

echo "Building/pulling wheelhouse for Home Assistant (may take a while first run)..."
set +e
${VENV_PYTHON} -m pip wheel --wheel-dir "${WHEEL_DIR}" --pre "homeassistant[tests]" || true
set -e

if [ -n "$(ls -A "${WHEEL_DIR}" 2>/dev/null)" ]; then
    echo "Installing Home Assistant from wheelhouse..."
    ${VENV_PYTHON} -m pip install --no-index --find-links "${WHEEL_DIR}" --pre "homeassistant[tests]"
else
    echo "Installing Home Assistant from PyPI (this may compile wheels)..."
    ${VENV_PYTHON} -m pip install --pre --prefer-binary "homeassistant[tests]"
fi

echo "Installing integration requirements from manifest..."
if command -v jq >/dev/null 2>&1; then
    for req in $(jq -c -r '.requirements | .[]' "${WORKSPACE_DIR}/custom_components/sharedcam/manifest.json"); do
        ${VENV_PYTHON} -m pip install "$req"
    done
fi

echo "Ensuring pytest and HA test plugin..."
${VENV_PYTHON} -m pip install -U pytest pytest-asyncio pytest-homeassistant-custom-component

echo "Setup complete. Activate the venv with: source ${VENV}/bin/activate"
