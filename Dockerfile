# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=app.py \
    FLASK_ENV=production

# Copy requirements first for better caching
COPY requirements.txt .

# Install system dependencies and Python packages
# Note: gcc is needed for compiling some Python packages (e.g., numpy)
# We remove it after installation to reduce image size
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . .

# Create directory for database (will be created as volume, but ensure parent exists)
RUN mkdir -p /app/data

# Expose port 5000
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]

