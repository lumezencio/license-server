"""
License Server - Main Application
Sistema de licenciamento profissional com RSA
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import settings
from app.database import init_db
from app.api import (
    auth_router,
    clients_router,
    licenses_router,
    validation_router,
    stats_router
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
