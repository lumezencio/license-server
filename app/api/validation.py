"""
License Server - Validation API
Endpoints públicos para ativação e validação de licenças
(Chamados pelo enterprise_system)
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import License, LicenseValidation, LicenseStatus, Client
from app.schemas import (
    LicenseActivateRequest,
    LicenseValidateRequest,
    LicenseValidateResponse
)
from app.core import rsa_manager

router = APIRouter(prefix="/v1", tags=["License Validation"])


def get_client_ip(request: Request) -> str:
    """Obtém IP real do cliente"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/activate", response_model=LicenseValidateResponse)
async def activate_license(
    request_data: LicenseActivateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Ativa uma licença vinculando ao hardware do cliente.
    Endpoint público (chamado pelo enterprise_system na primeira execução)
    """
    # Busca licença com eager loading do client
    result = await db.execute(
        select(License)
        .options(selectinload(License.client))
        .where(License.license_key == request_data.license_key)
    )
    license = result.scalar_one_or_none()

    if not license:
        # Registra tentativa falha
        validation = LicenseValidation(
            license_id=None,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent", "")[:500],
            hardware_id=request_data.hardware_id,
            validation_type="activation",
            success=False,
            error_message="License not found"
        )
        # Não salva pois license_id é obrigatório

        return LicenseValidateResponse(
            valid=False,
            status="error",
            message="License key not found"
        )

    # Verifica se já está ativada em outro hardware
    if license.hardware_id and license.hardware_id != request_data.hardware_id:
        validation = LicenseValidation(
            license_id=license.id,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent", "")[:500],
            hardware_id=request_data.hardware_id,
            validation_type="activation",
            success=False,
            error_message="License already activated on another hardware"
        )
        db.add(validation)
        await db.commit()

        return LicenseValidateResponse(
            valid=False,
            status="error",
            message="License already activated on another machine. Contact support."
        )

    # Verifica se licença foi revogada
    if license.status == LicenseStatus.REVOKED.value:
        return LicenseValidateResponse(
            valid=False,
            status="revoked",
            message="License has been revoked"
        )

    # Verifica expiração
    if license.expires_at and datetime.utcnow() > license.expires_at:
        license.status = LicenseStatus.EXPIRED.value
        await db.commit()

        return LicenseValidateResponse(
            valid=False,
            status="expired",
            message="License has expired"
        )

    # Ativa a licença
    license.hardware_id = request_data.hardware_id
    license.hardware_info = request_data.hardware_info or {}
    license.activated_at = datetime.utcnow()
    license.last_validated_at = datetime.utcnow()
    license.status = LicenseStatus.ACTIVE.value

    # Gera assinatura RSA
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

    # Registra validação bem sucedida
    validation = LicenseValidation(
        license_id=license.id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent", "")[:500],
        hardware_id=request_data.hardware_id,
        validation_type="activation",
        success=True
    )
    db.add(validation)
    await db.commit()

    return LicenseValidateResponse(
        valid=True,
        status="active",
        message="License activated successfully",
        license_key=license.license_key,
        plan=license.plan,
        features=license.features or [],
        expires_at=license.expires_at,
        days_until_expiry=license.days_until_expiry(),
        limits={
            "max_users": license.max_users,
            "max_customers": license.max_customers,
            "max_products": license.max_products,
            "max_monthly_transactions": license.max_monthly_transactions
        },
        signature=license.signature
    )


@router.post("/validate", response_model=LicenseValidateResponse)
async def validate_license(
    request_data: LicenseValidateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Valida licença (heartbeat periódico).
    Endpoint público (chamado pelo enterprise_system periodicamente)
    """
    # Busca licença com eager loading do client
    result = await db.execute(
        select(License)
        .options(selectinload(License.client))
        .where(License.license_key == request_data.license_key)
    )
    license = result.scalar_one_or_none()

    if not license:
        return LicenseValidateResponse(
            valid=False,
            status="error",
            message="License not found"
        )

    # Verifica hardware
    if license.hardware_id and license.hardware_id != request_data.hardware_id:
        validation = LicenseValidation(
            license_id=license.id,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent", "")[:500],
            hardware_id=request_data.hardware_id,
            validation_type="heartbeat",
            success=False,
            error_message="Hardware mismatch"
        )
        db.add(validation)
        await db.commit()

        return LicenseValidateResponse(
            valid=False,
            status="error",
            message="Hardware ID mismatch. License may be pirated."
        )

    # Verifica status
    if license.status == LicenseStatus.REVOKED.value:
        return LicenseValidateResponse(
            valid=False,
            status="revoked",
            message="License has been revoked"
        )

    if license.status == LicenseStatus.SUSPENDED.value:
        return LicenseValidateResponse(
            valid=False,
            status="suspended",
            message="License has been suspended. Contact support."
        )

    # Verifica expiração
    if license.expires_at and datetime.utcnow() > license.expires_at:
        license.status = LicenseStatus.EXPIRED.value
        await db.commit()

        return LicenseValidateResponse(
            valid=False,
            status="expired",
            message="License has expired",
            expires_at=license.expires_at
        )

    # Atualiza último heartbeat
    license.last_validated_at = datetime.utcnow()
    license.last_heartbeat_at = datetime.utcnow()

    # Registra validação
    validation = LicenseValidation(
        license_id=license.id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent", "")[:500],
        hardware_id=request_data.hardware_id,
        validation_type="heartbeat",
        success=True
    )
    db.add(validation)
    await db.commit()

    return LicenseValidateResponse(
        valid=True,
        status="active",
        message="License is valid",
        license_key=license.license_key,
        plan=license.plan,
        features=license.features or [],
        expires_at=license.expires_at,
        days_until_expiry=license.days_until_expiry(),
        limits={
            "max_users": license.max_users,
            "max_customers": license.max_customers,
            "max_products": license.max_products,
            "max_monthly_transactions": license.max_monthly_transactions
        },
        signature=license.signature
    )


@router.get("/public-key")
async def get_public_key():
    """
    Retorna chave pública RSA para verificação offline.
    O enterprise_system pode usar isso para validar assinaturas localmente.
    """
    return {
        "public_key": rsa_manager.get_public_key_pem(),
        "algorithm": "RSA-PSS",
        "hash": "SHA256"
    }


@router.get("/health")
async def health_check():
    """Health check para o license server"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "license-server",
        "version": "1.0.0"
    }
