"""
License Server - Main Application
Sistema de licenciamento profissional com RSA
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.core import settings
from app.database import init_db
from app.api import (
    auth_router,
    clients_router,
    licenses_router,
    validation_router,
    stats_router,
    register_router,
    provisioning_router,
    tenant_auth_router,
    tenant_gateway_router,
    payments_router
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle do aplicativo"""
    # Startup
    print(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"Environment: {settings.ENVIRONMENT}")

    # Inicializa banco de dados
    await init_db()
    print("Database initialized")

    yield

    # Shutdown
    print("Shutting down...")


# Cria aplicação
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Professional License Management System with RSA signatures",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router, prefix="/api")
app.include_router(clients_router, prefix="/api")
app.include_router(licenses_router, prefix="/api")
app.include_router(validation_router, prefix="/api")
app.include_router(stats_router, prefix="/api")
app.include_router(register_router, prefix="/api")
app.include_router(provisioning_router, prefix="/api")
app.include_router(tenant_auth_router, prefix="/api")
app.include_router(tenant_gateway_router, prefix="/api")
app.include_router(payments_router, prefix="/api")

# Static files para uploads
# Usa diretório relativo para desenvolvimento local e /app/uploads para produção
if os.path.exists("/app/uploads"):
    uploads_dir = "/app/uploads"
else:
    # Desenvolvimento local - cria pasta uploads na raiz do projeto
    uploads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")

os.makedirs(uploads_dir, exist_ok=True)
os.makedirs(os.path.join(uploads_dir, "logos"), exist_ok=True)
print(f"Uploads directory: {uploads_dir}")
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
