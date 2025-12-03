"""
License Server - Licenses API
CRUD e gerenciamento de licenças
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.database import get_db
from app.models import License, Client, AdminUser, LicenseStatus
from app.schemas import LicenseCreate, LicenseUpdate, LicenseResponse
from app.api.auth import get_current_admin
from app.core import generate_license_key, rsa_manager

router = APIRouter(prefix="/licenses", tags=["Licenses"])


@router.get("", response_model=List[LicenseResponse])
async def list_licenses(
    search: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    plan: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Lista todas as licenças"""
    query = select(License)

    if search:
        query = query.where(
            or_(
                License.license_key.ilike(f"%{search}%"),
                License.hardware_id.ilike(f"%{search}%")
            )
        )

    if client_id:
        query = query.where(License.client_id == client_id)

    if status:
        query = query.where(License.status == status)

    if plan:
        query = query.where(License.plan == plan)

    query = query.order_by(License.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    licenses = result.scalars().all()

    return [lic.to_dict() for lic in licenses]


@router.get("/{license_id}", response_model=LicenseResponse)
async def get_license(
    license_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Retorna uma licença específica"""
    result = await db.execute(
        select(License).where(License.id == license_id)
    )
    license = result.scalar_one_or_none()

    if not license:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License not found"
        )

    return license.to_dict()


@router.post("", response_model=LicenseResponse, status_code=status.HTTP_201_CREATED)
async def create_license(
    request: LicenseCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Cria nova licença"""
    # Verifica se cliente existe
    result = await db.execute(
        select(Client).where(Client.id == request.client_id)
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )

    if not client.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client is inactive"
        )

    # Gera chave única
    license_key = generate_license_key()

    # Garante unicidade
    while True:
        result = await db.execute(
            select(License).where(License.license_key == license_key)
        )
        if not result.scalar_one_or_none():
            break
        license_key = generate_license_key()

    license = License(
        license_key=license_key,
        client_id=request.client_id,
        plan=request.plan,
        features=request.features,
        max_users=request.max_users,
        max_customers=request.max_customers,
        max_products=request.max_products,
        max_monthly_transactions=request.max_monthly_transactions,
        expires_at=request.expires_at,
        is_trial=request.is_trial,
        notes=request.notes,
        status=LicenseStatus.PENDING.value
    )

    db.add(license)
    await db.commit()
    await db.refresh(license)

    return license.to_dict()


@router.put("/{license_id}", response_model=LicenseResponse)
async def update_license(
    license_id: str,
    request: LicenseUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Atualiza licença"""
    result = await db.execute(
        select(License).where(License.id == license_id)
    )
    license = result.scalar_one_or_none()

    if not license:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License not found"
        )

    update_data = request.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(license, field, value)

    # Regenera assinatura se licença está ativa
    if license.status == LicenseStatus.ACTIVE.value and license.hardware_id:
        license_data = {
            "license_key": license.license_key,
            "client_id": license.client_id,
            "client_name": license.client.name if license.client else "",
            "hardware_id": license.hardware_id,
            "plan": license.plan,
            "features": license.features or [],
            "max_users": license.max_users,
            "issued_at": license.issued_at.isoformat() if license.issued_at else None,
            "expires_at": license.expires_at.isoformat() if license.expires_at else None,
            "version": "1.0"
        }
        license.signature = rsa_manager.sign_license(license_data)

    await db.commit()
    await db.refresh(license)

    return license.to_dict()


@router.post("/{license_id}/revoke")
async def revoke_license(
    license_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Revoga uma licença"""
    result = await db.execute(
        select(License).where(License.id == license_id)
    )
    license = result.scalar_one_or_none()

    if not license:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License not found"
        )

    license.status = LicenseStatus.REVOKED.value
    await db.commit()

    return {"message": "License revoked successfully"}


@router.post("/{license_id}/suspend")
async def suspend_license(
    license_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Suspende uma licença temporariamente"""
    result = await db.execute(
        select(License).where(License.id == license_id)
    )
    license = result.scalar_one_or_none()

    if not license:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License not found"
        )

    license.status = LicenseStatus.SUSPENDED.value
    await db.commit()

    return {"message": "License suspended successfully"}


@router.post("/{license_id}/reactivate")
async def reactivate_license(
    license_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Reativa uma licença suspensa"""
    result = await db.execute(
        select(License).where(License.id == license_id)
    )
    license = result.scalar_one_or_none()

    if not license:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License not found"
        )

    if license.status not in [LicenseStatus.SUSPENDED.value, LicenseStatus.EXPIRED.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="License cannot be reactivated"
        )

    # Verifica se não expirou
    if license.expires_at and datetime.utcnow() > license.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="License has expired. Please extend the expiration date first."
        )

    license.status = LicenseStatus.ACTIVE.value
    await db.commit()

    return {"message": "License reactivated successfully"}


@router.get("/{license_id}/download")
async def download_license_file(
    license_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Download do arquivo de licença (para enviar ao cliente)"""
    result = await db.execute(
        select(License).where(License.id == license_id)
    )
    license = result.scalar_one_or_none()

    if not license:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License not found"
        )

    if not license.signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="License not activated yet"
        )

    return license.to_license_file()
