"""
License Server - Configuration
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional
import secrets
from pathlib import Path
from dotenv import load_dotenv

# Carrega .env com override para sobrescrever variáveis do sistema
# Isso é necessário porque pode haver DATABASE_URL global no sistema
env_file = Path(__file__).parent.parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file, override=True)


class Settings(BaseSettings):
    # App
    APP_NAME: str = "License Server"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8080

    # Database (accepts DATABASE_URL or LICENSE_DATABASE_URL)
    DATABASE_URL: Optional[str] = None
    LICENSE_DATABASE_URL: str = "sqlite+aiosqlite:///./licenses.db"

    @property
    def db_url(self) -> str:
        """Returns DATABASE_URL if set, otherwise LICENSE_DATABASE_URL"""
        return self.DATABASE_URL or self.LICENSE_DATABASE_URL

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

    # Email Settings (SMTP)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "noreply@tech-emp.com"
    SMTP_FROM_NAME: str = "Tech-EMP Sistema"
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False

    # App URLs
    APP_URL: str = "https://www.tech-emp.com"
    LOGIN_URL: str = "https://www.tech-emp.com/login"

    # PostgreSQL Master (para criar bancos de tenants)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DATABASE: str = "postgres"

    class Config:
        extra = "ignore"
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
