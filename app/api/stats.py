"""
License Server - Statistics API
Dashboard e estatísticas para admin
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import License, Client, LicenseValidation, AdminUser, LicenseStatus
from app.api.auth import get_current_admin

router = APIRouter(prefix="/stats", tags=["Statistics"])


@router.get("/dashboard")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Estatísticas para o dashboard admin"""

    # Total de clientes
    result = await db.execute(select(func.count(Client.id)))
    total_clients = result.scalar() or 0

    result = await db.execute(
        select(func.count(Client.id)).where(Client.is_active == True)
    )
    active_clients = result.scalar() or 0

    # Total de licenças
    result = await db.execute(select(func.count(License.id)))
    total_licenses = result.scalar() or 0

    # Licenças por status
    result = await db.execute(
        select(func.count(License.id)).where(License.status == LicenseStatus.ACTIVE.value)
    )
    active_licenses = result.scalar() or 0

    result = await db.execute(
        select(func.count(License.id)).where(License.status == LicenseStatus.EXPIRED.value)
    )
    expired_licenses = result.scalar() or 0

    result = await db.execute(
        select(func.count(License.id)).where(License.status == LicenseStatus.PENDING.value)
    )
    pending_licenses = result.scalar() or 0

    # Licenças expirando em 30 dias
    thirty_days = datetime.utcnow() + timedelta(days=30)
    result = await db.execute(
        select(func.count(License.id)).where(
            License.status == LicenseStatus.ACTIVE.value,
            License.expires_at <= thirty_days,
            License.expires_at > datetime.utcnow()
        )
    )
    expiring_soon = result.scalar() or 0

    # Licenças por plano
    result = await db.execute(
        select(License.plan, func.count(License.id))
        .group_by(License.plan)
    )
    licenses_by_plan = {row[0]: row[1] for row in result.all()}

    # Validações últimas 24h
    yesterday = datetime.utcnow() - timedelta(days=1)
    result = await db.execute(
        select(func.count(LicenseValidation.id)).where(
            LicenseValidation.created_at >= yesterday
        )
    )
    validations_24h = result.scalar() or 0

    # Validações falhas últimas 24h
    result = await db.execute(
        select(func.count(LicenseValidation.id)).where(
            LicenseValidation.created_at >= yesterday,
            LicenseValidation.success == False
        )
    )
    failed_validations_24h = result.scalar() or 0

    return {
        "clients": {
            "total": total_clients,
            "active": active_clients
        },
        "licenses": {
            "total": total_licenses,
            "active": active_licenses,
            "expired": expired_licenses,
            "pending": pending_licenses,
            "expiring_soon": expiring_soon,
            "by_plan": licenses_by_plan
        },
        "validations": {
            "last_24h": validations_24h,
            "failed_24h": failed_validations_24h
        },
        "generated_at": datetime.utcnow().isoformat()
    }


@router.get("/licenses/expiring")
async def get_expiring_licenses(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Lista licenças que vão expirar em X dias"""
    future_date = datetime.utcnow() + timedelta(days=days)

    result = await db.execute(
        select(License)
        .where(
            License.status == LicenseStatus.ACTIVE.value,
            License.expires_at <= future_date,
            License.expires_at > datetime.utcnow()
        )
        .order_by(License.expires_at)
    )
    licenses = result.scalars().all()

    return [lic.to_dict() for lic in licenses]


@router.get("/validations/recent")
async def get_recent_validations(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Lista validações recentes"""
    result = await db.execute(
        select(LicenseValidation)
        .order_by(LicenseValidation.created_at.desc())
        .limit(limit)
    )
    validations = result.scalars().all()

    return [v.to_dict() for v in validations]


@router.get("/validations/failed")
async def get_failed_validations(
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin)
):
    """Lista validações falhas recentes (possíveis tentativas de pirataria)"""
    since = datetime.utcnow() - timedelta(hours=hours)

    result = await db.execute(
        select(LicenseValidation)
        .where(
            LicenseValidation.success == False,
            LicenseValidation.created_at >= since
        )
        .order_by(LicenseValidation.created_at.desc())
    )
    validations = result.scalars().all()

    return [v.to_dict() for v in validations]
