# Use Fedora as base image
# Fedora aligns with Red Hat ecosystem (relevant for OpenShift deployment)
FROM registry.fedoraproject.org/fedora:41

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=app.py \
    FLASK_ENV=production

# Install Python and dependencies
# - gcc: needed for compiling some Python packages
# - curl: needed for healthcheck
RUN dnf install -y python3 python3-pip gcc curl && \
    dnf clean all

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python packages
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Generate demo template databases (ensures templates match current code)
RUN python3 scripts/create_demo_templates.py

# Create directory for database (will be created as volume, but ensure parent exists)
RUN mkdir -p /app/data

# Expose port 5000
EXPOSE 5000

# Run the application with Gunicorn (production WSGI server)
# - workers: 3 processes (max for 1 vCPU, handles concurrent demo users)
# - timeout: 5s (demo mode has no uploads, all ops are fast)
# - access-logfile: log requests to stdout for container logging
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "--timeout", "5", "--access-logfile", "-", "app:app"]

