FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package management
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy dependency files and package metadata
COPY pyproject.toml uv.lock README.md ./

# Install Python dependencies before copying the local project.
RUN uv sync --frozen --no-install-project

# Copy application code
COPY *.py ./
COPY git_host_keys ./git_host_keys
COPY relay_sdk ./relay_sdk
COPY templates ./templates
COPY run.sh ./
RUN chmod +x run.sh

# Install the local console command.
RUN uv sync --frozen

# Create data directory for persistent storage
RUN mkdir -p /data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Run the application. Docker command arguments are passed to app.py.
ENTRYPOINT ["./run.sh"]
