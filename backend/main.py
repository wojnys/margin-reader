"""Compatibility entry point. Prefer backend.app.main:create_app --factory."""
from backend.app.main import create_app
app = create_app()
