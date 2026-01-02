# Gunicorn configuration file
# Used by both Dockerfile (CMD) and S2I (APP_CONFIG)

# Binding
bind = "0.0.0.0:8080"  # S2I expects 8080, not 5000

# Workers
workers = 3  # Max for 1 vCPU, handles concurrent demo users

# Timeout
timeout = 30  # Reasonable for demo mode

# Logging
accesslog = "-"  # Log to stdout for container logging
errorlog = "-"   # Log to stderr
loglevel = "info"

# Security
limit_request_line = 4094
limit_request_fields = 100
