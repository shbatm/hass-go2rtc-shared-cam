ARG VARIANT="debian"
FROM mcr.microsoft.com/vscode/devcontainers/base:${VARIANT}

# Install system packages needed for building Python packages and Home Assistant tests
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      python3-dev \
      python3-venv \
  python3-pip \
  # python3-distutils is not available on some Debian releases (e.g. trixie).
  # Use python3-setuptools which provides the necessary distutils support
  # for building Python packages on these images.
  python3-setuptools \
  python3-full \
      git \
      curl \
      jq \
      ca-certificates \
      libssl-dev \
      libffi-dev \
      libjpeg-dev \
      zlib1g-dev \
      pkg-config \
      cargo \
    && rm -rf /var/lib/apt/lists/*

# Create a venv for the workspace during image build so pip is available
# This avoids bootstrapping pip at container runtime which can hit PEP 668 issues
RUN mkdir -p /workspaces/go2rtc-shared-cam \
  && python3 -m venv /workspaces/go2rtc-shared-cam/.venv \
  && /workspaces/go2rtc-shared-cam/.venv/bin/python -m pip install -U pip setuptools wheel || true

# Also create a prebuilt venv in /opt/venv to copy into the workspace at runtime
RUN python3 -m venv /opt/venv \
  && /opt/venv/bin/python -m pip install -U pip setuptools wheel || true

# Make sure the venvs are writable by the non-root 'vscode' user so the container
# user can install packages into them during postCreate/setup (avoids permission errors).
RUN chown -R vscode:vscode /opt/venv /workspaces/go2rtc-shared-cam/.venv || true
