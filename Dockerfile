# Hubfeed Agent Dockerfile

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (including Chrome for NoDriver browser automation)
RUN apt-get update && apt-get install -y \
    gcc \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY ui/ ./ui/

# Create directories for persistent data
RUN mkdir -p /app/data /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    AGENT_UI_USERNAME=admin \
    AGENT_UI_PASSWORD=changeme \
    BROWSER_HEADLESS=true

# Expose port
EXPOSE 8989

# Run the application
CMD ["python", "-m", "src.main"]
