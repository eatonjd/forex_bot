# Use official Python runtime
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (includes models directory)
COPY . .

# Environment variables will be set via Cloud Run
ENV PYTHONUNBUFFERED=1

# Health check endpoint
EXPOSE 8080

# Run the bot with health check server
CMD ["python", "-u", "cloud_run_server.py"]
