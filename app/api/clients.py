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
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Remove cliente (soft delete - desativa)"""
    result = await db.execute(
        select(Client).where(Client.id == client_id)
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    # Soft delete
    client.is_active = False
    await db.commit()

    return {"message": "Client deactivated successfully"}
