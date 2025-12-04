"""
License Server - Configuration
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional
import secrets


class Settings(BaseSettings):
    # App
    APP_NAME: str = "License Server"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8080

    # Database (use LICENSE_DATABASE_URL to avoid conflict with other projects)
    LICENSE_DATABASE_URL: str = "sqlite+aiosqlite:///./licenses.db"

    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "RS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # RSA Keys (geradas na inicialização se não existirem)
    RSA_PRIVATE_KEY_PATH: str = "keys/private_key.pem"
    RSA_PUBLIC_KEY_PATH: str = "keys/public_key.pem"

    # License Settings
    LICENSE_GRACE_PERIOD_DAYS: int = 7
    LICENSE_HEARTBEAT_INTERVAL_HOURS: int = 4
    LICENSE_VALIDATION_CACHE_HOURS: int = 24

    # Admin
    ADMIN_EMAIL: str = "admin@license-server.com"
    ADMIN_PASSWORD: str = "change-me-in-production"

    # CORS
    CORS_ORIGINS: list = ["*"]

    class Config:
        extra = "ignore"
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
