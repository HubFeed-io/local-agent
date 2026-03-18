# Hubfeed Agent Dockerfile

FROM ubuntu:22.04

EXPOSE 8989 5900

# Set working directory
WORKDIR /app

# Install system dependencies + Python 3.10
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-venv \
    python3-pip \
    xvfb \
    x11vnc \
    fluxbox \
    wget \
    unzip \
    gnupg2 \
    apt-utils \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install Chromium browser (works on both amd64 and arm64)
# Ubuntu 22.04's chromium-browser is a snap wrapper that doesn't work in Docker,
# so we install real Chromium .deb from Debian bookworm repos instead.
RUN gpg --keyserver keyserver.ubuntu.com --recv-keys 6ED0E7B82643E131 F8D2585B8783D481 \
    && gpg --export 6ED0E7B82643E131 F8D2585B8783D481 > /usr/share/keyrings/debian-bookworm.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/debian-bookworm.gpg] http://deb.debian.org/debian bookworm main" > /etc/apt/sources.list.d/debian-bookworm.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends -t bookworm chromium \
    && rm -rf /var/lib/apt/lists/* /etc/apt/sources.list.d/debian-bookworm.list /root/.gnupg \
    && which chromium

# Set up VNC password (1234)
RUN mkdir -p ~/.vnc && x11vnc -storepasswd 1234 ~/.vnc/passwd

# Copy requirements first for better caching
COPY requirements.txt /tmp/requirements.txt

# Install Python dependencies in a venv
RUN python3.10 -m venv /py \
    && /py/bin/pip install --upgrade pip \
    && /py/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Copy application code
COPY src/ ./src/
COPY ui/ ./ui/

# Create directories for persistent data
RUN mkdir -p /app/data /app/logs

# Copy entrypoint
COPY entrypoint.sh /scripts/entrypoint.sh
RUN chmod +x /scripts/entrypoint.sh

# Set environment variables
ENV PATH="/scripts:/py/bin:$PATH" \
    DISPLAY=:0 \
    PYTHONUNBUFFERED=1


ENTRYPOINT ["entrypoint.sh"]
