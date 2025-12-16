"""
License Server - Database Session
"""
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger(__name__)

# Engine assíncrono
engine = create_async_engine(
    settings.db_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# Base para models
Base = declarative_base()


async def get_db() -> AsyncSession:
    """Dependency para injetar sessão do banco"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def verify_admin_integrity():
    """
    Verifica integridade do admin na inicialização.
    Se o hash estiver corrompido (não começa com $2b$), restaura para senha padrão.

    IMPORTANTE: Isso garante que o admin sempre tenha acesso ao sistema,
    mesmo se o hash for corrompido por comandos SSH mal-formados.
    """
    import bcrypt

    async with AsyncSessionLocal() as session:
        try:
            # Busca o admin principal
            result = await session.execute(
                text("SELECT id, email, hashed_password FROM admin_users WHERE is_superadmin = true LIMIT 1")
            )
            admin = result.fetchone()

            if not admin:
                logger.warning("Nenhum admin superadmin encontrado")
                return

            admin_id, email, hashed_password = admin

            # Verifica se o hash está válido (deve começar com $2b$ ou $2a$)
            if not hashed_password or not hashed_password.startswith(('$2b$', '$2a$')):
                logger.error(f"ALERTA: Hash do admin {email} está CORROMPIDO!")
                logger.error(f"Hash atual: {hashed_password[:20] if hashed_password else 'NULL'}...")

                # Gera novo hash com senha padrão
                default_password = settings.ADMIN_PASSWORD or "admin123"
                new_hash = bcrypt.hashpw(default_password.encode(), bcrypt.gensalt(12)).decode()

                # Atualiza no banco
                await session.execute(
                    text("UPDATE admin_users SET hashed_password = :hash WHERE id = :id"),
                    {"hash": new_hash, "id": admin_id}
                )
                await session.commit()

                logger.info(f"Hash do admin {email} foi RESTAURADO!")
                logger.info(f"Nova senha: {default_password}")
            else:
                logger.info(f"Admin {email} - hash válido (bcrypt)")

        except Exception as e:
            logger.error(f"Erro ao verificar integridade do admin: {e}")
            await session.rollback()


async def init_db():
    """Inicializa banco de dados (cria tabelas) e verifica integridade do admin"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Verifica e corrige admin se necessário
    await verify_admin_integrity()
