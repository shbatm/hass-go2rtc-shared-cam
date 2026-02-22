#!/usr/bin/env bash
set -euo pipefail

# Create .homeassistant runtime directory and symlink custom_components for development
# Idempotent: will not overwrite an existing .homeassistant directory
# Also ensures go2rtc binary is present and executable

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RUNTIME_DIR="$REPO_ROOT/.homeassistant"
DEV_CONFIG="$REPO_ROOT/.devcontainer/configuration.yaml"
GO2RTC_BIN="$RUNTIME_DIR/go2rtc"

echo "[setup_homeassistant_runtime] repo_root=$REPO_ROOT"

# Function to download and setup go2rtc binary
setup_go2rtc() {
  local target="$1"

  # If go2rtc exists and is executable, we're done
  if [ -x "$target" ]; then
    echo "[setup_homeassistant_runtime] go2rtc already exists at $target"
    return 0
  fi

  echo "[setup_homeassistant_runtime] downloading go2rtc binary..."

  local api_url="https://api.github.com/repos/AlexxIT/go2rtc/releases/latest"
  local download_url

  # Get the latest release download URL for linux_amd64
  download_url=$(curl -fsSL "$api_url" | grep -o '"browser_download_url": "[^"]*go2rtc_linux_amd64[^"]*"' | head -1 | cut -d'"' -f4)

  if [ -z "$download_url" ]; then
    echo "[setup_homeassistant_runtime] ERROR: could not find go2rtc_linux_amd64 download URL"
    return 1
  fi

  echo "[setup_homeassistant_runtime] downloading from: $download_url"

  # Download with temporary file, then rename
  local temp_file=$(mktemp)
  if curl -fsSL -o "$temp_file" "$download_url"; then
    mv "$temp_file" "$target"
    chmod +x "$target"
    echo "[setup_homeassistant_runtime] go2rtc binary installed successfully"
  else
    rm -f "$temp_file"
    echo "[setup_homeassistant_runtime] ERROR: failed to download go2rtc"
    return 1
  fi
}

# Function to download and setup Frigate integration
setup_frigate() {
  local target_dir="$1"
  local repo_url="https://github.com/blakeblackshear/frigate-hass-integration"
  local source_path="custom_components/frigate"

  echo "[setup_homeassistant_runtime] setting up Frigate integration..."

  # Create temporary directory for download
  local temp_dir=$(mktemp -d)
  trap "rm -rf '$temp_dir'" RETURN

  # Clone the repo (sparse checkout for efficiency)
  if git -C "$temp_dir" clone --depth 1 --filter=blob:none --sparse "$repo_url" frigate-repo 2>/dev/null; then
    if git -C "$temp_dir/frigate-repo" sparse-checkout set "$source_path" 2>/dev/null; then
      # Copy the frigate component to target
      if [ -d "$temp_dir/frigate-repo/$source_path" ]; then
        rm -rf "$target_dir"  # Remove existing to get fresh copy
        cp -r "$temp_dir/frigate-repo/$source_path" "$target_dir"
        echo "[setup_homeassistant_runtime] Frigate integration installed successfully"
        return 0
      fi
    fi
  fi

  # Fallback: try full clone if sparse checkout fails
  echo "[setup_homeassistant_runtime] sparse checkout failed, trying full clone..."
  if git -C "$temp_dir" clone --depth 1 "$repo_url" frigate-repo 2>/dev/null; then
    if [ -d "$temp_dir/frigate-repo/$source_path" ]; then
      rm -rf "$target_dir"
      cp -r "$temp_dir/frigate-repo/$source_path" "$target_dir"
      echo "[setup_homeassistant_runtime] Frigate integration installed successfully"
      return 0
    fi
  fi

  echo "[setup_homeassistant_runtime] ERROR: failed to download Frigate integration"
  return 1
}

if [ -d "$RUNTIME_DIR" ] && [ -f "$RUNTIME_DIR/configuration.yaml" ]; then
  echo "[setup_homeassistant_runtime] $RUNTIME_DIR already exists with configuration.yaml — will refresh components"
fi

mkdir -p "$RUNTIME_DIR"

# Ensure custom_components directory exists
mkdir -p "$RUNTIME_DIR/custom_components"

if [ -f "$DEV_CONFIG" ]; then
  if [ ! -f "$RUNTIME_DIR/configuration.yaml" ]; then
    cp "$DEV_CONFIG" "$RUNTIME_DIR/configuration.yaml"
    echo "[setup_homeassistant_runtime] copied default configuration to $RUNTIME_DIR/configuration.yaml"
  else
    echo "[setup_homeassistant_runtime] configuration.yaml already exists in $RUNTIME_DIR — skipping copy"
  fi
else
  echo "[setup_homeassistant_runtime] warning: $DEV_CONFIG not found — no default configuration copied"
fi

## Create symlink for sharedcam component (points to repo's sharedcam)
# Safety: never remove repository files. Only remove a runtime copy if its resolved
# path is inside the runtime directory.
if [ -e "$RUNTIME_DIR/custom_components/sharedcam" ] && [ ! -L "$RUNTIME_DIR/custom_components/sharedcam" ]; then
  real_target=$(realpath "$RUNTIME_DIR/custom_components/sharedcam" 2>/dev/null || true)
  real_runtime=$(realpath "$RUNTIME_DIR" 2>/dev/null || true)
  if [ -n "$real_target" ] && [ -n "$real_runtime" ] && [[ "$real_target" == "$real_runtime"* ]]; then
    echo "[setup_homeassistant_runtime] migrating sharedcam from directory to symlink..."
    rm -rf "$RUNTIME_DIR/custom_components/sharedcam"
  else
    echo "[setup_homeassistant_runtime] WARNING: $RUNTIME_DIR/custom_components/sharedcam exists outside runtime; skipping removal"
  fi
fi

if [ -L "$RUNTIME_DIR/custom_components/sharedcam" ]; then
  echo "[setup_homeassistant_runtime] sharedcam symlink already exists"
else
  ln -s "$REPO_ROOT/custom_components/sharedcam" "$RUNTIME_DIR/custom_components/sharedcam"
  echo "[setup_homeassistant_runtime] created symlink $RUNTIME_DIR/custom_components/sharedcam -> $REPO_ROOT/custom_components/sharedcam"
fi

# Ensure go2rtc binary is downloaded and executable
setup_go2rtc "$GO2RTC_BIN" || true

# Ensure Frigate integration is downloaded and available
setup_frigate "$RUNTIME_DIR/custom_components/frigate" || true

echo "[setup_homeassistant_runtime] done"
