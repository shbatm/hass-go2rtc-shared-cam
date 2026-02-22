#!/usr/bin/env bash
# Idempotent refresh helper for .homeassistant runtime folder.
# Use when you want to re-copy the default configuration or re-create the symlink.
# Also ensures go2rtc binary is present and executable.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd -P)"
cd "$repo_root"

echo "[refresh_homeassistant_runtime] repo_root=$repo_root"

# Function to download and setup go2rtc binary
setup_go2rtc() {
  local target="$1"

  # If go2rtc exists and is executable, we're done
  if [ -x "$target" ]; then
    echo "[refresh_homeassistant_runtime] go2rtc already exists at $target"
    return 0
  fi

  echo "[refresh_homeassistant_runtime] downloading go2rtc binary..."

  local api_url="https://api.github.com/repos/AlexxIT/go2rtc/releases/latest"
  local download_url

  # Get the latest release download URL for linux_amd64
  download_url=$(curl -fsSL "$api_url" | grep -o '"browser_download_url": "[^"]*go2rtc_linux_amd64[^"]*"' | head -1 | cut -d'"' -f4)

  if [ -z "$download_url" ]; then
    echo "[refresh_homeassistant_runtime] ERROR: could not find go2rtc_linux_amd64 download URL"
    return 1
  fi

  echo "[refresh_homeassistant_runtime] downloading from: $download_url"

  # Download with temporary file, then rename
  local temp_file=$(mktemp)
  if curl -fsSL -o "$temp_file" "$download_url"; then
    mv "$temp_file" "$target"
    chmod +x "$target"
    echo "[refresh_homeassistant_runtime] go2rtc binary installed successfully"
  else
    rm -f "$temp_file"
    echo "[refresh_homeassistant_runtime] ERROR: failed to download go2rtc"
    return 1
  fi
}

# Function to download and setup Frigate integration
setup_frigate() {
  local target_dir="$1"
  local repo_url="https://github.com/blakeblackshear/frigate-hass-integration"
  local source_path="custom_components/frigate"

  echo "[refresh_homeassistant_runtime] updating Frigate integration..."

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
        echo "[refresh_homeassistant_runtime] Frigate integration updated successfully"
        return 0
      fi
    fi
  fi

  # Fallback: try full clone if sparse checkout fails
  echo "[refresh_homeassistant_runtime] sparse checkout failed, trying full clone..."
  if git -C "$temp_dir" clone --depth 1 "$repo_url" frigate-repo 2>/dev/null; then
    if [ -d "$temp_dir/frigate-repo/$source_path" ]; then
      rm -rf "$target_dir"
      cp -r "$temp_dir/frigate-repo/$source_path" "$target_dir"
      echo "[refresh_homeassistant_runtime] Frigate integration updated successfully"
      return 0
    fi
  fi

  echo "[refresh_homeassistant_runtime] ERROR: failed to download Frigate integration"
  return 1
}

if [ -d "$repo_root/.homeassistant" ]; then
  echo "[refresh_homeassistant_runtime] $repo_root/.homeassistant exists"
else
  echo "[refresh_homeassistant_runtime] $repo_root/.homeassistant missing, creating"
  mkdir -p "$repo_root/.homeassistant"
fi

# Ensure custom_components directory exists
mkdir -p "$repo_root/.homeassistant/custom_components"

# Copy configuration.yaml only if upstream devcontainer copy exists
if [ -f "$repo_root/.devcontainer/configuration.yaml" ]; then
  echo "[refresh_homeassistant_runtime] copying $repo_root/.devcontainer/configuration.yaml -> $repo_root/.homeassistant/configuration.yaml"
  cp -n "$repo_root/.devcontainer/configuration.yaml" "$repo_root/.homeassistant/configuration.yaml" || true
else
  echo "[refresh_homeassistant_runtime] no $repo_root/.devcontainer/configuration.yaml to copy"
fi

## Create symlink for sharedcam component (points to repo's sharedcam)
# Safety: never remove repository files. Only remove a runtime copy if its resolved
# path is inside the runtime directory.
if [ -e "$repo_root/.homeassistant/custom_components/sharedcam" ] && [ ! -L "$repo_root/.homeassistant/custom_components/sharedcam" ]; then
  real_target=$(realpath "$repo_root/.homeassistant/custom_components/sharedcam" 2>/dev/null || true)
  real_runtime=$(realpath "$repo_root/.homeassistant" 2>/dev/null || true)
  if [ -n "$real_target" ] && [ -n "$real_runtime" ] && [[ "$real_target" == "$real_runtime"* ]]; then
    echo "[refresh_homeassistant_runtime] migrating sharedcam from directory to symlink..."
    rm -rf "$repo_root/.homeassistant/custom_components/sharedcam"
  else
    echo "[refresh_homeassistant_runtime] WARNING: $repo_root/.homeassistant/custom_components/sharedcam exists outside runtime; skipping removal"
  fi
fi

if [ -L "$repo_root/.homeassistant/custom_components/sharedcam" ]; then
  echo "[refresh_homeassistant_runtime] sharedcam symlink already exists"
else
  echo "[refresh_homeassistant_runtime] creating symlink for sharedcam"
  ln -s "$repo_root/custom_components/sharedcam" "$repo_root/.homeassistant/custom_components/sharedcam"
fi

# Remove old blanket custom_components symlink if it exists (migration from old setup).
# The old setup used a single symlink: .homeassistant/custom_components -> ../custom_components
# The new setup uses .homeassistant/custom_components/ as a real directory with per-component symlinks.
# Detect the old layout by checking whether custom_components itself is a symlink.
if [ -L "$repo_root/.homeassistant/custom_components" ]; then
  echo "[refresh_homeassistant_runtime] removing old blanket custom_components symlink..."
  rm "$repo_root/.homeassistant/custom_components"
  mkdir -p "$repo_root/.homeassistant/custom_components"
fi

# Ensure go2rtc binary is downloaded and executable
setup_go2rtc "$repo_root/.homeassistant/go2rtc" || true

# Ensure Frigate integration is downloaded and available
setup_frigate "$repo_root/.homeassistant/custom_components/frigate" || true

echo "[refresh_homeassistant_runtime] done"
