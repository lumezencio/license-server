"""
License Server - License Expiration Task
Verifica periodicamente licencas expiradas e atualiza status automaticamente.

Este modulo roda em background e:
1. A cada 5 minutos verifica licencas com status ACTIVE cujo expires_at ja passou
2. Atualiza o status para EXPIRED no banco
3. Log de cada licenca expirada para auditoria
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update, and_

from app.database import AsyncSessionLocal
from app.models.license import License, LicenseStatus

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 300  # 5 minutos


async def expire_licenses():
    """
    Busca licencas ACTIVE com expires_at no passado e marca como EXPIRED.
    Operacao idempotente e segura — so atualiza status, nao deleta nada.
    """
    try:
        async with AsyncSessionLocal() as db:
            now = datetime.utcnow()

            # Busca licencas ativas que ja expiraram
            result = await db.execute(
                select(License).where(
                    and_(
                        License.status == LicenseStatus.ACTIVE.value,
                        License.expires_at != None,
                        License.expires_at < now,
                    )
                )
            )
            expired_licenses = result.scalars().all()

            if not expired_licenses:
                return 0

            count = 0
            for lic in expired_licenses:
                old_status = lic.status
                lic.status = LicenseStatus.EXPIRED.value
                lic.updated_at = now
                count += 1
                logger.warning(
                    f"[LICENSE-EXPIRATION] Licenca {lic.license_key} expirada "
                    f"(cliente={lic.client_id}, plano={lic.plan}, "
                    f"expirou_em={lic.expires_at.isoformat()}, "
                    f"status {old_status} -> expired)"
                )

            await db.commit()

            if count > 0:
                logger.info(
                    f"[LICENSE-EXPIRATION] {count} licenca(s) marcada(s) como expirada(s)"
                )

            return count

    except Exception as e:
        logger.error(f"[LICENSE-EXPIRATION] Erro ao verificar expiracoes: {e}")
        import traceback
        traceback.print_exc()
        return 0


async def run_expiration_task():
    """
    Loop principal do task de expiracao.
    Executa a cada CHECK_INTERVAL_SECONDS verificando licencas expiradas.
    """
    logger.info("[LICENSE-EXPIRATION] ========================================")
    logger.info("[LICENSE-EXPIRATION] Servico de expiracao automatica INICIADO")
    logger.info(f"[LICENSE-EXPIRATION] Intervalo: {CHECK_INTERVAL_SECONDS}s")
    logger.info("[LICENSE-EXPIRATION] ========================================")

    # Primeira execucao imediata ao iniciar
    count = await expire_licenses()
    if count > 0:
        logger.info(f"[LICENSE-EXPIRATION] Execucao inicial: {count} licenca(s) expirada(s)")

    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            await expire_licenses()
        except asyncio.CancelledError:
            logger.info("[LICENSE-EXPIRATION] Task cancelado (shutdown)")
            break
        except Exception as e:
            logger.error(f"[LICENSE-EXPIRATION] Erro no loop: {e}")
            await asyncio.sleep(60)  # Espera 1min antes de tentar novamente
