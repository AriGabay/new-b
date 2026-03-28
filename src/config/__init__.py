"""
System configuration.

Config is loaded once at startup from YAML/env and passed into groups.
No group reads environment variables or files directly.

Source: /docs/architecture/runtime_model.md
"""
from .settings import SystemConfig, load_config

__all__ = ["SystemConfig", "load_config"]
