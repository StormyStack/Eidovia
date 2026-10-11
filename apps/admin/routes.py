"""
Legacy compatibility bridge:
Exposes admin_router from the modular admin package structure.
"""

from admin import admin_router as router

__all__ = ["router"]
