"""
License Server - Provisioning API
Endpoints para provisionamento de tenants
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models import Tenant, TenantStatus, License, LicenseStatus
from app.core import provisioning_service, settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/provisioning", tags=["Provisioning"])


class ProvisionRequest(BaseModel):
    """Request para provisionar um tenant"""
    tenant_id: str


class ProvisionResponse(BaseModel):
    """Response do provisionamento"""
    success: bool
    message: str
    tenant_id: str
    database_name: Optional[str] = None
    database_url: Optional[str] = None


class TenantStatusResponse(BaseModel):
    """Status do tenant"""
    tenant_id: str
    tenant_code: str
    status: str
    database_name: Optional[str] = None
    is_provisioned: bool
    provisioned_at: Optional[datetime] = None


async def provision_tenant_task(
    tenant_id: str,
    db_session_factory
):
    """
    Task em background para provisionar tenant.
    Esta função é executada após o endpoint retornar.
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            # Busca o tenant
            result = await db.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            )
            tenant = result.scalar_one_or_none()

            if not tenant:
                logger.error(f"Tenant {tenant_id} não encontrado para provisioning")
                return

            # Atualiza status para PROVISIONING
            tenant.status = TenantStatus.PROVISIONING.value
            await db.commit()

            # Executa provisionamento
            success, message = await provisioning_service.provision_tenant(
                tenant_code=tenant.tenant_code,
                database_name=tenant.database_name,
                database_user=tenant.database_user,
                database_password=tenant.database_password,
                admin_email=tenant.email,
                admin_password=tenant.document,  # CPF/CNPJ como senha inicial
                admin_name=tenant.name
            )

            if success:
                # Atualiza tenant com sucesso
                tenant.status = TenantStatus.TRIAL.value if tenant.is_trial else TenantStatus.ACTIVE.value
                tenant.provisioned_at = datetime.utcnow()
                tenant.database_host = settings.POSTGRES_HOST
                tenant.database_port = settings.POSTGRES_PORT
                tenant.database_url = tenant.get_database_url()

                # Ativa a licença
                if tenant.client_id:
                    license_result = await db.execute(
                        select(License).where(License.client_id == tenant.client_id)
                    )
                    license = license_result.scalar_one_or_none()
                    if license:
                        license.status = LicenseStatus.ACTIVE.value

                await db.commit()
                logger.info(f"Tenant {tenant.tenant_code} provisionado com sucesso")

            else:
                # Marca como erro
                tenant.status = TenantStatus.PENDING.value
                tenant.metadata_ = tenant.metadata_ or {}
                tenant.metadata_["provisioning_error"] = message
                await db.commit()
                logger.error(f"Erro no provisionamento do tenant {tenant.tenant_code}: {message}")

        except Exception as e:
            logger.error(f"Erro fatal no provisionamento: {e}")
            try:
                tenant.status = TenantStatus.PENDING.value
                await db.commit()
            except:
                pass


@router.post("/provision", response_model=ProvisionResponse)
async def provision_tenant(
    request: ProvisionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Inicia o provisionamento de um tenant.

    O provisionamento é executado em background e inclui:
    - Criação do banco de dados PostgreSQL
    - Criação do usuário com permissões
    - Criação das tabelas do sistema
    - Criação do usuário admin inicial
    - Ativação da licença
    """
    # Busca o tenant
    result = await db.execute(
        select(Tenant).where(Tenant.id == request.tenant_id)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant não encontrado"
        )

    # Verifica se já está provisionado
    if tenant.status in [TenantStatus.ACTIVE.value, TenantStatus.TRIAL.value]:
        return ProvisionResponse(
            success=True,
            message="Tenant já está provisionado",
            tenant_id=tenant.id,
            database_name=tenant.database_name,
            database_url=tenant.get_database_url()
        )

    # Verifica se está em provisionamento
    if tenant.status == TenantStatus.PROVISIONING.value:
        return ProvisionResponse(
            success=False,
            message="Provisionamento já em andamento",
            tenant_id=tenant.id
        )

    # Verifica dados necessários
    if not tenant.database_name or not tenant.database_user or not tenant.database_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dados de banco de dados não configurados para este tenant"
        )

    # Inicia provisionamento em background
    background_tasks.add_task(provision_tenant_task, tenant.id, None)

    return ProvisionResponse(
        success=True,
        message="Provisionamento iniciado. O banco de dados será criado em alguns segundos.",
        tenant_id=tenant.id,
        database_name=tenant.database_name
    )


@router.post("/provision-sync", response_model=ProvisionResponse)
async def provision_tenant_sync(
    request: ProvisionRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Provisiona um tenant de forma síncrona (aguarda conclusão).
    Use apenas para testes ou quando precisar do resultado imediato.
    """
    # Busca o tenant
    result = await db.execute(
        select(Tenant).where(Tenant.id == request.tenant_id)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant não encontrado"
        )

    # Verifica se já está provisionado
    if tenant.status in [TenantStatus.ACTIVE.value, TenantStatus.TRIAL.value]:
        return ProvisionResponse(
            success=True,
            message="Tenant já está provisionado",
            tenant_id=tenant.id,
            database_name=tenant.database_name,
            database_url=tenant.get_database_url()
        )

    # Atualiza status
    tenant.status = TenantStatus.PROVISIONING.value
    await db.commit()

    try:
        # Executa provisionamento
        success, message = await provisioning_service.provision_tenant(
            tenant_code=tenant.tenant_code,
            database_name=tenant.database_name,
            database_user=tenant.database_user,
            database_password=tenant.database_password,
            admin_email=tenant.email,
            admin_password=tenant.document,
            admin_name=tenant.name
        )

        if success:
            tenant.status = TenantStatus.TRIAL.value if tenant.is_trial else TenantStatus.ACTIVE.value
            tenant.provisioned_at = datetime.utcnow()
            tenant.database_host = settings.POSTGRES_HOST
            tenant.database_port = settings.POSTGRES_PORT
            tenant.database_url = tenant.get_database_url()

            # Ativa a licença
            if tenant.client_id:
                license_result = await db.execute(
                    select(License).where(License.client_id == tenant.client_id)
                )
                license = license_result.scalar_one_or_none()
                if license:
                    license.status = LicenseStatus.ACTIVE.value

            await db.commit()

            return ProvisionResponse(
                success=True,
                message="Provisionamento concluído com sucesso",
                tenant_id=tenant.id,
                database_name=tenant.database_name,
                database_url=tenant.get_database_url()
            )
        else:
            tenant.status = TenantStatus.PENDING.value
            await db.commit()

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro no provisionamento: {message}"
            )

    except HTTPException:
        raise
    except Exception as e:
        tenant.status = TenantStatus.PENDING.value
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro inesperado: {str(e)}"
        )


@router.get("/status/{tenant_id}", response_model=TenantStatusResponse)
async def get_provisioning_status(
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Retorna o status do provisionamento de um tenant"""
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant não encontrado"
        )

    is_provisioned = tenant.status in [
        TenantStatus.ACTIVE.value,
        TenantStatus.TRIAL.value
    ]

    return TenantStatusResponse(
        tenant_id=tenant.id,
        tenant_code=tenant.tenant_code,
        status=tenant.status,
        database_name=tenant.database_name,
        is_provisioned=is_provisioned,
        provisioned_at=tenant.provisioned_at
    )


@router.get("/check-database/{tenant_id}")
async def check_tenant_database(
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Verifica a saúde do banco de dados de um tenant"""
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant não encontrado"
        )

    if not tenant.provisioned_at:
        return {
            "tenant_id": tenant.id,
            "status": "not_provisioned",
            "message": "Banco de dados ainda não foi provisionado"
        }

    # Verifica o banco
    success, info = await provisioning_service.check_tenant_database(
        database_name=tenant.database_name,
        username=tenant.database_user,
        password=tenant.database_password
    )

    return {
        "tenant_id": tenant.id,
        "database_name": tenant.database_name,
        "status": "healthy" if success else "error",
        "info": info
    }


@router.get("/pending")
async def list_pending_tenants(
    db: AsyncSession = Depends(get_db)
):
    """Lista todos os tenants pendentes de provisionamento"""
    result = await db.execute(
        select(Tenant).where(Tenant.status == TenantStatus.PENDING.value)
    )
    tenants = result.scalars().all()

    return {
        "count": len(tenants),
        "tenants": [
            {
                "id": t.id,
                "tenant_code": t.tenant_code,
                "name": t.name,
                "email": t.email,
                "registered_at": t.registered_at.isoformat() if t.registered_at else None
            }
            for t in tenants
        ]
    }


@router.post("/provision-all")
async def provision_all_pending(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Provisiona todos os tenants pendentes"""
    result = await db.execute(
        select(Tenant).where(Tenant.status == TenantStatus.PENDING.value)
    )
    tenants = result.scalars().all()

    if not tenants:
        return {
            "message": "Nenhum tenant pendente",
            "count": 0
        }

    # Adiciona todos ao background
    for tenant in tenants:
        background_tasks.add_task(provision_tenant_task, tenant.id, None)

    return {
        "message": f"Provisionamento iniciado para {len(tenants)} tenant(s)",
        "count": len(tenants),
        "tenants": [t.tenant_code for t in tenants]
    }
