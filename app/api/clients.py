"""
License Server - Clients API
CRUD de clientes (empresas que compram licenças)
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.database import get_db
from app.models import Client, AdminUser
from app.schemas import ClientCreate, ClientUpdate, ClientResponse
from app.api.auth import get_current_admin

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.get("", response_model=List[ClientResponse])
async def list_clients(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Lista todos os clientes"""
    query = select(Client)

    if search:
        query = query.where(
            or_(
                Client.name.ilike(f"%{search}%"),
                Client.email.ilike(f"%{search}%"),
                Client.document.ilike(f"%{search}%")
            )
        )

    if is_active is not None:
        query = query.where(Client.is_active == is_active)

    query = query.order_by(Client.name).offset(skip).limit(limit)

    result = await db.execute(query)
    clients = result.scalars().all()

    return [c.to_dict() for c in clients]


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Retorna um cliente específico"""
    result = await db.execute(
        select(Client).where(Client.id == client_id)
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    return client.to_dict()


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    request: ClientCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Cria novo cliente"""
    # Verifica email único
    result = await db.execute(
        select(Client).where(Client.email == request.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Verifica documento único (se fornecido)
    if request.document:
        result = await db.execute(
            select(Client).where(Client.document == request.document)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document already registered"
            )

    client = Client(**request.model_dump())
    db.add(client)
    await db.commit()
    await db.refresh(client)

    return client.to_dict()


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: str,
    request: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Atualiza cliente"""
    result = await db.execute(
        select(Client).where(Client.id == client_id)
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    update_data = request.model_dump(exclude_unset=True)

    # Verifica unicidade de email
    if "email" in update_data and update_data["email"] != client.email:
        result = await db.execute(
            select(Client).where(Client.email == update_data["email"])
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use"
            )

    for field, value in update_data.items():
        setattr(client, field, value)

    await db.commit()
    await db.refresh(client)

    return client.to_dict()


@router.delete("/{client_id}")
async def delete_client(
    client_id: str,
    permanent: bool = Query(False, description="Se True, exclui permanentemente incluindo tenant e banco"),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """
    Remove cliente.
    - permanent=False (padrão): apenas desativa o cliente (soft delete)
    - permanent=True: EXCLUI TUDO - banco de dados do tenant, usuário PostgreSQL,
      tenant, licenças e cliente. Operação irreversível!
    """
    from app.models import License, Tenant
    import asyncpg
    import logging
    import os

    logger = logging.getLogger(__name__)

    result = await db.execute(
        select(Client).where(Client.id == client_id)
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente não encontrado"
        )

    if not permanent:
        # Soft delete - apenas desativa
        client.is_active = False
        await db.commit()
        return {"message": "Cliente desativado com sucesso", "client_id": client_id}

    # ========== EXCLUSÃO PERMANENTE ==========
    logger.info(f"[DELETE-CLIENT] Iniciando exclusão permanente do cliente {client_id} ({client.name})")

    deleted_items = {
        "database": False,
        "db_user": False,
        "tenant": False,
        "licenses": 0,
        "client": False
    }

    # 1. Buscar tenant associado
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.client_id == client_id)
    )
    tenant = tenant_result.scalar_one_or_none()

    if tenant:
        logger.info(f"[DELETE-CLIENT] Tenant encontrado: {tenant.tenant_code}")

        # 2. Excluir banco de dados e usuário PostgreSQL do tenant
        try:
            # Configuração do PostgreSQL master
            postgres_host = os.environ.get("POSTGRES_HOST", "license-db")
            if postgres_host == "localhost":
                postgres_host = "license-db"

            # Extrair credenciais do DATABASE_URL
            database_url = os.environ.get("DATABASE_URL", "")
            postgres_user = "license_admin"
            postgres_password = "changeme"

            if database_url:
                import re
                match = re.search(r'://([^:]+):([^@]+)@', database_url)
                if match:
                    postgres_user = match.group(1)
                    postgres_password = match.group(2)

            # Conectar ao PostgreSQL master
            conn = await asyncpg.connect(
                host=postgres_host,
                port=5432,
                user=postgres_user,
                password=postgres_password,
                database="postgres"
            )

            try:
                database_name = tenant.database_name or f"cliente_{tenant.tenant_code}"
                db_user = tenant.database_user or f"user_{tenant.tenant_code}"

                # Forçar desconexão de todas as sessões do banco
                await conn.execute(f"""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = '{database_name}' AND pid <> pg_backend_pid()
                """)

                # Excluir banco de dados
                await conn.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
                deleted_items["database"] = True
                logger.info(f"[DELETE-CLIENT] Banco de dados '{database_name}' excluído")

                # Excluir usuário PostgreSQL
                await conn.execute(f'DROP USER IF EXISTS "{db_user}"')
                deleted_items["db_user"] = True
                logger.info(f"[DELETE-CLIENT] Usuário PostgreSQL '{db_user}' excluído")

            finally:
                await conn.close()

        except Exception as e:
            logger.warning(f"[DELETE-CLIENT] Erro ao excluir banco/usuário (pode não existir): {e}")

        # 3. Excluir tenant da tabela
        await db.delete(tenant)
        deleted_items["tenant"] = True
        logger.info(f"[DELETE-CLIENT] Tenant {tenant.tenant_code} excluído da tabela")

    # 4. Excluir licenças
    licenses_result = await db.execute(
        select(License).where(License.client_id == client_id)
    )
    licenses = licenses_result.scalars().all()

    for license in licenses:
        await db.delete(license)
        deleted_items["licenses"] += 1

    if deleted_items["licenses"] > 0:
        logger.info(f"[DELETE-CLIENT] {deleted_items['licenses']} licença(s) excluída(s)")

    # 5. Excluir cliente
    await db.delete(client)
    deleted_items["client"] = True

    await db.commit()
    logger.info(f"[DELETE-CLIENT] Cliente {client.name} ({client_id}) excluído permanentemente")

    return {
        "message": "Cliente excluído permanentemente com sucesso",
        "client_id": client_id,
        "client_name": client.name,
        "deleted": deleted_items
    }
