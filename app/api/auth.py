"""
License Server - Auth API
Autenticação de administradores
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import AdminUser, Tenant
from app.schemas import LoginRequest, LoginResponse, AdminUserCreate, AdminUserResponse
from app.core import (
    verify_password,
    get_password_hash,
    create_access_token,
    verify_access_token,
    settings
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> AdminUser:
    """Dependency para obter admin autenticado"""
    token = credentials.credentials
    payload = verify_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    result = await db.execute(
        select(AdminUser).where(AdminUser.id == payload.get("sub"))
    )
    admin = result.scalar_one_or_none()

    if not admin or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    return admin


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login de administrador"""
    result = await db.execute(
        select(AdminUser).where(AdminUser.email == request.email)
    )
    admin = result.scalar_one_or_none()

    if not admin or not verify_password(request.password, admin.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled"
        )

    # Atualiza último login
    admin.last_login_at = datetime.utcnow()
    await db.commit()

    # Gera token
    access_token = create_access_token(
        data={"sub": admin.id, "email": admin.email},
        expires_delta=timedelta(hours=24)
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=admin.to_dict()
    )


@router.get("/me", response_model=AdminUserResponse)
async def get_me(admin: AdminUser = Depends(get_current_admin)):
    """Retorna dados do admin atual"""
    return admin.to_dict()


@router.post("/register", response_model=AdminUserResponse)
async def register_admin(
    request: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin)
):
    """Registra novo admin (apenas superadmin pode)"""
    if not current_admin.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmin can create new admins"
        )

    # Verifica se email já existe
    result = await db.execute(
        select(AdminUser).where(AdminUser.email == request.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    admin = AdminUser(
        email=request.email,
        hashed_password=get_password_hash(request.password),
        full_name=request.full_name,
        is_superadmin=request.is_superadmin
    )

    db.add(admin)
    await db.commit()
    await db.refresh(admin)

    return admin.to_dict()


@router.post("/setup")
async def initial_setup(db: AsyncSession = Depends(get_db)):
    """Setup inicial - cria admin padrão se não existir"""
    result = await db.execute(select(AdminUser).limit(1))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Setup already completed"
        )

    admin = AdminUser(
        email=settings.ADMIN_EMAIL,
        hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
        full_name="Administrator",
        is_superadmin=True
    )

    db.add(admin)
    await db.commit()

    return {"message": "Setup completed", "email": settings.ADMIN_EMAIL}


# ============================================
# ADMIN - TENANTS ENDPOINT
# ============================================
@router.get("/admin/tenants")
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin)
):
    """Lista todos os tenants com informacao do produto"""
    result = await db.execute(
        select(Tenant).order_by(Tenant.registered_at.desc())
    )
    tenants = result.scalars().all()

    return [
        {
            "id": t.id,
            "tenant_code": t.tenant_code,
            "name": t.name,
            "trade_name": t.trade_name,
            "email": t.email,
            "document": t.document,
            "phone": t.phone,
            "product_code": t.product_code,
            "status": t.status,
            "is_trial": t.is_trial,
            "trial_days": t.trial_days,
            "trial_expires_at": t.trial_expires_at.isoformat() if t.trial_expires_at else None,
            "database_name": t.database_name,
            "registered_at": t.registered_at.isoformat() if t.registered_at else None,
            "provisioned_at": t.provisioned_at.isoformat() if t.provisioned_at else None,
            "activated_at": t.activated_at.isoformat() if t.activated_at else None,
        }
        for t in tenants
    ]
