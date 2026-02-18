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
    ALGORITHM: str = "HS256"  # HS256 para chaves simetricas (SECRET_KEY string)
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

    # CORS - URLs específicas para allow_credentials=True
    CORS_ORIGINS: list = [
        "https://www.tech-emp.com",
        "https://tech-emp.com",
        "https://admin.tech-emp.com",
        "https://enterprise.softwarecorp.com.br",
        "https://www.softwarecorp.com.br",
        "https://softwarecorp.com.br",
        "https://botwhatsapp.softwarecorp.com.br",
        "https://api.botwhatsapp.softwarecorp.com.br",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001"
    ]

    # Email Settings (SMTP)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "noreply@tech-emp.com"
    SMTP_FROM_NAME: str = "Tech-EMP Sistema"
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False

    # Resend API (alternativa quando SMTP estiver bloqueado)
    RESEND_API_KEY: Optional[str] = None
    EMAIL_PROVIDER: str = "smtp"  # "smtp" ou "resend"

    # Email de notificação de erros
    ERROR_NOTIFICATION_EMAIL: str = "lucianomezencio@gmail.com"
    ERROR_NOTIFICATION_ENABLED: bool = True

    # App URLs (default para Enterprise/Tech-EMP)
    APP_URL: str = "https://www.tech-emp.com"
    LOGIN_URL: str = "https://www.tech-emp.com/login"

    # URLs por produto
    PRODUCT_URLS: dict = {
        "enterprise": {
            "app_url": "https://enterprise.softwarecorp.com.br",
            "login_url": "https://enterprise.softwarecorp.com.br/login",
            "name": "Enterprise",
            "company": "SoftwareCorp"
        },
        "tech-emp": {
            "app_url": "https://www.tech-emp.com",
            "login_url": "https://www.tech-emp.com/login",
            "name": "Tech-EMP",
            "company": "Tech-EMP"
        },
        "condotech": {
            "app_url": "https://condotech.softwarecorp.com.br",
            "login_url": "https://condotech.softwarecorp.com.br/login",
            "name": "CondoTech",
            "company": "SoftwareCorp"
        },
        "diario": {
            "app_url": "https://meu-diario.softwarecorp.com.br",
            "login_url": "https://meu-diario.softwarecorp.com.br/login",
            "name": "Meu-Diario",
            "company": "SoftwareCorp"
        },
        "botwhatsapp": {
            "app_url": "https://botwhatsapp.softwarecorp.com.br",
            "login_url": "https://botwhatsapp.softwarecorp.com.br/login",
            "name": "WhatsApp Bot Manager",
            "company": "SoftwareCorp"
        }
    }

    def get_product_url(self, product_code: str, url_type: str = "login_url") -> str:
        """Retorna a URL correta para o produto especificado."""
        product = self.PRODUCT_URLS.get(product_code.lower(), self.PRODUCT_URLS.get("enterprise"))
        return product.get(url_type, self.LOGIN_URL)

    # PostgreSQL Master (para criar bancos de tenants)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DATABASE: str = "postgres"

    # Mercado Pago
    MP_ACCESS_TOKEN: str = ""  # Access Token do Mercado Pago
    MP_PUBLIC_KEY: str = ""    # Public Key do Mercado Pago
    MP_WEBHOOK_SECRET: str = ""  # Secret para validar webhooks (assinatura secreta)
    MP_SANDBOX: bool = True    # True = ambiente de teste, False = produção

    class Config:
        extra = "ignore"
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
