from .auth import router as auth_router
from .clients import router as clients_router
from .licenses import router as licenses_router
from .validation import router as validation_router
from .stats import router as stats_router
from .register import router as register_router
from .provisioning import router as provisioning_router
from .tenant_auth import router as tenant_auth_router
from .tenant_gateway import router as tenant_gateway_router

__all__ = [
    "auth_router",
    "clients_router",
    "licenses_router",
    "validation_router",
    "stats_router",
    "register_router",
    "provisioning_router",
    "tenant_auth_router",
    "tenant_gateway_router"
]
