from .auth import router as auth_router
from .clients import router as clients_router
from .licenses import router as licenses_router
from .validation import router as validation_router
from .stats import router as stats_router

__all__ = [
    "auth_router",
    "clients_router",
    "licenses_router",
    "validation_router",
    "stats_router"
]
