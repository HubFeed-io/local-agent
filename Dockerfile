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

# Install Google Chrome
RUN wget --no-check-certificate https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && dpkg -i google-chrome-stable_current_amd64.deb || true \
    && apt-get update && apt-get install -fy --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* google-chrome-stable_current_amd64.deb \
    && which google-chrome-stable || (echo 'Google Chrome was not installed' && exit 1)

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
