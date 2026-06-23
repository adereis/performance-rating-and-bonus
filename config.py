"""Application configuration.

A small Config object centralizes environment-driven settings and enforces the
production SECRET_KEY requirement. Previously SECRET_KEY silently fell back to a
dev key even in production (publicly visible in the repo); Config makes that a
fail-fast error instead. See docs/REFACTOR_APP_SPLIT.md (Phase 7).
"""
import os

# Dev-only fallback key. Used only outside production so local runs and the test
# suite work without configuration; never used when FLASK_ENV=production.
DEV_SECRET_KEY = 'dev-only-insecure-key-change-in-production'


class Config:
    """Runtime configuration resolved from environment variables.

    Construct once at startup (create_app). Raises RuntimeError if SECRET_KEY is
    missing while FLASK_ENV=production, so misconfigured production deployments
    fail loudly at boot rather than serving with a known, public key.
    """

    def __init__(self):
        self.FLASK_ENV = os.getenv('FLASK_ENV', '')
        self.is_production = self.FLASK_ENV == 'production'
        self.DEMO_MODE = os.getenv('DEMO_MODE', 'false').lower() == 'true'
        # Cap upload size (Workday XLSX exports are small; 10 MB is generous).
        self.MAX_CONTENT_LENGTH = int(os.getenv('MAX_UPLOAD_MB', '10')) * 1024 * 1024
        self.SECRET_KEY = self._resolve_secret_key()

    def _resolve_secret_key(self):
        secret = os.getenv('SECRET_KEY')
        if secret:
            return secret
        if self.is_production:
            raise RuntimeError(
                "SECRET_KEY environment variable is required when "
                "FLASK_ENV=production. Generate one with:\n"
                '  export SECRET_KEY=$(python3 -c "import secrets; '
                'print(secrets.token_hex(32))")'
            )
        return DEV_SECRET_KEY
