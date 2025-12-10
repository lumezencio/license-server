"""
License Server - Tenant Authentication API
Sistema de login unico multi-tenant
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional
import hashlib
import asyncpg

from app.database import get_db
from app.models import Tenant, TenantStatus, License, LicenseStatus
from app.core import settings, create_access_token
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenant-auth", tags=["Tenant Authentication"])


class TenantLoginRequest(BaseModel):
    """Request de login multi-tenant"""
    email: EmailStr
    password: str


class TenantLoginResponse(BaseModel):
    """Response do login multi-tenant"""
    success: bool
    message: str
    tenant_code: Optional[str] = None
    tenant_name: Optional[str] = None
    database_url: Optional[str] = None
    api_url: Optional[str] = None
    access_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[dict] = None
    requires_password_change: bool = False
    is_trial: bool = False
    trial_expires_at: Optional[datetime] = None
    # Dados da licença real
    license_plan: Optional[str] = None
    license_expires_at: Optional[datetime] = None
    license_status: Optional[str] = None
    license_days_remaining: Optional[int] = None
    license_key: Optional[str] = None


class TenantInfoResponse(BaseModel):
    """Informacoes publicas do tenant"""
    tenant_code: str
    name: str
    trade_name: Optional[str] = None
    status: str
    is_trial: bool
    trial_expires_at: Optional[datetime] = None
    is_trial_valid: bool


async def verify_tenant_user(
    database_host: str,
    database_port: int,
    database_name: str,
    database_user: str,
    database_password: str,
    email: str,
    password: str
) -> Optional[dict]:
    """
    Verifica credenciais do usuario no banco do tenant.
    Usa estrutura do enterprise_system: hashed_password, full_name, role, must_change_password

    Returns:
        dict com dados do usuario se autenticado, None caso contrario
    """
    try:
        logger.info(f"Conectando ao banco {database_name} em {database_host}:{database_port} como {database_user}")
        conn = await asyncpg.connect(
            host=database_host,
            port=database_port,
            user=database_user,
            password=database_password,
            database=database_name
        )

        try:
            # Busca usuario na tabela users (estrutura enterprise_system)
            user = await conn.fetchrow("""
                SELECT id, email, hashed_password, full_name, is_active, role,
                       COALESCE(must_change_password, false) as must_change_password
                FROM users
                WHERE email = $1 AND (deleted_at IS NULL OR deleted_at > CURRENT_TIMESTAMP)
            """, email.lower())

            if not user:
                logger.info(f"Usuario nao encontrado: {email}")
                return None

            if not user['is_active']:
                logger.info(f"Usuario inativo: {email}")
                return None

            # Verifica senha - tenta SHA256 primeiro (novos tenants), depois bcrypt (legado)
            password_valid = False
            password_hash_sha256 = hashlib.sha256(password.encode()).hexdigest()

            if user['hashed_password'] == password_hash_sha256:
                password_valid = True
                logger.info(f"Senha validada via SHA256 para: {email}")
            else:
                # Tenta bcrypt para usuarios legados
                import bcrypt
                try:
                    password_valid = bcrypt.checkpw(
                        password.encode(),
                        user['hashed_password'].encode()
                    )
                    if password_valid:
                        logger.info(f"Senha validada via bcrypt para: {email}")
                except Exception:
                    password_valid = False

            if not password_valid:
                logger.info(f"Senha invalida para: {email}")
                return None

            # Atualiza last_login_at
            try:
                await conn.execute("""
                    UPDATE users SET last_login_at = $1, updated_at = $1 WHERE id = $2
                """, datetime.utcnow(), user['id'])
            except Exception:
                pass  # Ignora erro ao atualizar last_login

            # Determina is_admin pelo role
            role = user.get('role', '') or ''
            is_admin = role in ['admin', 'superadmin']

            return {
                "id": str(user['id']),
                "email": user['email'],
                "name": user['full_name'] or '',
                "is_admin": is_admin,
                "must_change_password": user['must_change_password'] or False
            }

        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Erro ao verificar usuario no tenant: {e}")
        return None


@router.post("/login", response_model=TenantLoginResponse)
async def tenant_login(
    request: TenantLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Login multi-tenant.

    O sistema:
    1. Busca o tenant pelo email do usuario
    2. Verifica se o tenant esta ativo
    3. Valida credenciais no banco do tenant
    4. Retorna informacoes de acesso
    """
    email = request.email.lower()

    # 1. Busca tenant pelo email principal
    result = await db.execute(
        select(Tenant).where(Tenant.email == email)
    )
    tenant = result.scalar_one_or_none()

    # 1b. Se nao encontrou pelo email principal, busca usuario em todos os tenants ativos
    if not tenant:
        # Busca tenants ativos e provisionados
        tenants_result = await db.execute(
            select(Tenant).where(
                Tenant.provisioned_at.isnot(None),
                Tenant.status.in_([TenantStatus.ACTIVE.value, TenantStatus.TRIAL.value])
            )
        )
        active_tenants = tenants_result.scalars().all()

        # Tenta encontrar o usuario em cada tenant
        for t in active_tenants:
            user = await verify_tenant_user(
                t.database_host or settings.POSTGRES_HOST,
                t.database_port or settings.POSTGRES_PORT,
                t.database_name,
                t.database_user,
                t.database_password,
                email,
                request.password
            )
            if user:
                tenant = t
                break

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos"
        )

    # 2. Verifica status do tenant
    if tenant.status == TenantStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sua conta ainda esta sendo configurada. Aguarde o email de confirmacao."
        )

    if tenant.status == TenantStatus.PROVISIONING.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sua conta esta sendo preparada. Tente novamente em alguns minutos."
        )

    if tenant.status == TenantStatus.SUSPENDED.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sua conta esta suspensa. Entre em contato com o suporte."
        )

    if tenant.status == TenantStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sua conta foi cancelada."
        )

    if tenant.status == TenantStatus.TRIAL_EXPIRED.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seu periodo de avaliacao expirou. Entre em contato para contratar um plano."
        )

    # 3. Verifica trial expirado
    if tenant.is_trial and tenant.trial_expires_at:
        if datetime.utcnow() > tenant.trial_expires_at:
            tenant.status = TenantStatus.TRIAL_EXPIRED.value
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Seu periodo de avaliacao expirou. Entre em contato para contratar um plano."
            )

    # 4. Verifica licenca
    license_info = None
    if tenant.client_id:
        license_result = await db.execute(
            select(License).where(License.client_id == tenant.client_id)
        )
        license = license_result.scalar_one_or_none()

        if license:
            # Guarda info da licença para retornar
            license_info = {
                "plan": license.plan,
                "expires_at": license.expires_at,
                "status": license.status,
                "days_remaining": license.days_until_expiry(),
                "is_trial": license.is_trial,
                "license_key": license.license_key
            }

            if license.status == LicenseStatus.SUSPENDED.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Sua licenca esta suspensa. Entre em contato com o suporte."
                )
            if license.status == LicenseStatus.REVOKED.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Sua licenca foi revogada."
                )
            if license.status == LicenseStatus.EXPIRED.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Sua licenca expirou. Entre em contato para renovar."
                )

    # 5. Verifica se banco esta provisionado
    if not tenant.provisioned_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sua conta ainda esta sendo configurada. Aguarde alguns minutos."
        )

    # 6. Verifica credenciais no banco do tenant
    # Primeiro tentativa: senha informada
    user = await verify_tenant_user(
        tenant.database_host or settings.POSTGRES_HOST,
        tenant.database_port or settings.POSTGRES_PORT,
        tenant.database_name,
        tenant.database_user,
        tenant.database_password,
        email,
        request.password
    )

    # Se nao autenticou e senha nunca foi trocada, tenta com documento
    if not user and not tenant.password_changed:
        # Primeira tentativa com o documento puro
        user = await verify_tenant_user(
            tenant.database_host or settings.POSTGRES_HOST,
            tenant.database_port or settings.POSTGRES_PORT,
            tenant.database_name,
            tenant.database_user,
            tenant.database_password,
            email,
            tenant.document
        )

        if user and request.password == tenant.document:
            # Usuario logou com senha inicial
            pass
        elif user:
            # Senha informada nao e a inicial nem a correta
            user = None

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos"
        )

    # 7. Gera token de acesso
    token_data = {
        "sub": user["email"],
        "tenant_code": tenant.tenant_code,
        "user_id": user["id"],
        "is_admin": user["is_admin"]
    }
    access_token = create_access_token(
        data=token_data,
        expires_delta=timedelta(hours=8)
    )

    # 8. Monta URL da API do tenant
    # SISTEMA MULTI-TENANT: Usa API Gateway centralizado no License Server
    # O gateway autentica pelo JWT e roteia para o banco correto do tenant
    if tenant.custom_domain:
        api_url = f"https://{tenant.custom_domain}/api/v1"
    elif tenant.subdomain:
        api_url = f"https://{tenant.subdomain}.tech-emp.com/api/v1"
    else:
        # Usa API Gateway multi-tenant no License Server
        # Todas as requisicoes vao para /api/gateway/* e sao roteadas pelo tenant do token JWT
        api_url = f"https://license.tech-emp.com/api/gateway"

    # Determina is_trial baseado na licença (prioritário) ou tenant
    is_trial_final = license_info["is_trial"] if license_info else tenant.is_trial

    return TenantLoginResponse(
        success=True,
        message="Login realizado com sucesso",
        tenant_code=tenant.tenant_code,
        tenant_name=tenant.trade_name or tenant.name,
        database_url=tenant.get_database_url(),
        api_url=api_url,
        access_token=access_token,
        token_type="bearer",
        user=user,
        requires_password_change=user.get("must_change_password", False),
        is_trial=is_trial_final,
        trial_expires_at=tenant.trial_expires_at,
        # Dados da licença real
        license_plan=license_info["plan"] if license_info else None,
        license_expires_at=license_info["expires_at"] if license_info else None,
        license_status=license_info["status"] if license_info else None,
        license_days_remaining=license_info["days_remaining"] if license_info else None,
        license_key=license_info["license_key"] if license_info else None
    )


@router.get("/tenant/{tenant_code}", response_model=TenantInfoResponse)
async def get_tenant_public_info(
    tenant_code: str,
    db: AsyncSession = Depends(get_db)
):
    """Retorna informacoes publicas do tenant (para tela de login)"""
    result = await db.execute(
        select(Tenant).where(Tenant.tenant_code == tenant_code)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa nao encontrada"
        )

    return TenantInfoResponse(
        tenant_code=tenant.tenant_code,
        name=tenant.name,
        trade_name=tenant.trade_name,
        status=tenant.status,
        is_trial=tenant.is_trial,
        trial_expires_at=tenant.trial_expires_at,
        is_trial_valid=tenant.is_trial_valid()
    )


@router.post("/change-password")
async def change_tenant_password(
    tenant_code: str,
    email: EmailStr,
    current_password: str,
    new_password: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Troca a senha do usuario no banco do tenant.
    Usado principalmente no primeiro acesso.
    """
    # Busca tenant
    result = await db.execute(
        select(Tenant).where(Tenant.tenant_code == tenant_code)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa nao encontrada"
        )

    if not tenant.provisioned_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Conta ainda nao foi configurada"
        )

    # Verifica senha atual
    user = await verify_tenant_user(
        tenant.database_host or settings.POSTGRES_HOST,
        tenant.database_port or settings.POSTGRES_PORT,
        tenant.database_name,
        tenant.database_user,
        tenant.database_password,
        email,
        current_password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Senha atual incorreta"
        )

    # Valida nova senha
    if len(new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A nova senha deve ter no minimo 6 caracteres"
        )

    # Atualiza senha no banco do tenant
    try:
        conn = await asyncpg.connect(
            host=tenant.database_host or settings.POSTGRES_HOST,
            port=tenant.database_port or settings.POSTGRES_PORT,
            user=tenant.database_user,
            password=tenant.database_password,
            database=tenant.database_name
        )

        try:
            new_hash = hashlib.sha256(new_password.encode()).hexdigest()
            await conn.execute("""
                UPDATE users
                SET hashed_password = $1, must_change_password = FALSE, updated_at = $2
                WHERE email = $3
            """, new_hash, datetime.utcnow(), email.lower())

        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Erro ao trocar senha: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao trocar senha"
        )

    # Marca que senha foi trocada no tenant
    if not tenant.password_changed:
        tenant.password_changed = True
        tenant.activated_at = datetime.utcnow()
        await db.commit()

    return {
        "success": True,
        "message": "Senha alterada com sucesso"
    }


@router.get("/check-email/{email}")
async def check_email_tenant(
    email: EmailStr,
    db: AsyncSession = Depends(get_db)
):
    """
    Verifica se um email esta cadastrado e retorna info do tenant.
    Usado para pre-carregar informacoes na tela de login.
    """
    result = await db.execute(
        select(Tenant).where(Tenant.email == email.lower())
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        return {
            "found": False,
            "message": "Email nao encontrado"
        }

    return {
        "found": True,
        "tenant_code": tenant.tenant_code,
        "tenant_name": tenant.trade_name or tenant.name,
        "status": tenant.status,
        "is_trial": tenant.is_trial
    }
