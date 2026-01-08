"""
License Server - Tenant Authentication API
Sistema de login unico multi-tenant
Inclui recuperacao de senha por email
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional
import hashlib
import asyncpg
import secrets
import uuid

from app.database import get_db
from app.models import Tenant, TenantStatus, License, LicenseStatus
from app.core import settings, create_access_token
from app.core.email import email_service
import logging

# Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Limiter para protecao contra brute force
limiter = Limiter(key_func=get_remote_address)

# Cache simples para rastrear tentativas falhas por IP/email (em memoria)
# Em producao com multiplas instancias, usar Redis
from collections import defaultdict
import time

class LoginAttemptTracker:
    """Rastreia tentativas de login falhas para protecao contra brute force"""
    def __init__(self, max_attempts: int = 5, lockout_minutes: int = 15):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_minutes * 60
        self.attempts = defaultdict(list)  # key -> list of timestamps

    def _clean_old_attempts(self, key: str):
        """Remove tentativas antigas (mais de lockout_seconds)"""
        now = time.time()
        self.attempts[key] = [t for t in self.attempts[key] if now - t < self.lockout_seconds]

    def record_failed_attempt(self, ip: str, email: str):
        """Registra uma tentativa falha"""
        key = f"{ip}:{email.lower()}"
        self._clean_old_attempts(key)
        self.attempts[key].append(time.time())

    def is_locked(self, ip: str, email: str) -> tuple[bool, int]:
        """
        Verifica se IP/email esta bloqueado.
        Returns: (is_locked, remaining_seconds)
        """
        key = f"{ip}:{email.lower()}"
        self._clean_old_attempts(key)

        if len(self.attempts[key]) >= self.max_attempts:
            oldest = min(self.attempts[key])
            remaining = int(self.lockout_seconds - (time.time() - oldest))
            if remaining > 0:
                return True, remaining
        return False, 0

    def clear_attempts(self, ip: str, email: str):
        """Limpa tentativas apos login bem-sucedido"""
        key = f"{ip}:{email.lower()}"
        self.attempts.pop(key, None)

# Instancia global do tracker
login_tracker = LoginAttemptTracker(max_attempts=5, lockout_minutes=15)

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
@limiter.limit("5/minute")
async def tenant_login(
    login_data: TenantLoginRequest,
    request: Request,
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
    email = login_data.email.lower()
    client_ip = get_remote_address(request)

    # 0. Verifica se IP/email esta bloqueado por tentativas falhas
    is_locked, remaining_seconds = login_tracker.is_locked(client_ip, email)
    if is_locked:
        minutes = remaining_seconds // 60
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Muitas tentativas de login. Tente novamente em {minutes} minutos."
        )

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
                login_data.password
            )
            if user:
                tenant = t
                break

    if not tenant:
        # Registra tentativa falha
        login_tracker.record_failed_attempt(client_ip, email)
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
        login_data.password
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

        if user and login_data.password == tenant.document:
            # Usuario logou com senha inicial
            pass
        elif user:
            # Senha informada nao e a inicial nem a correta
            user = None

    if not user:
        # Registra tentativa falha
        login_tracker.record_failed_attempt(client_ip, email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos"
        )

    # Login bem-sucedido - limpa tentativas falhas
    login_tracker.clear_attempts(client_ip, email)

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
    # Prioridade: 1) api_url do banco, 2) custom_domain, 3) subdomain, 4) fallback por produto
    if tenant.api_url:
        api_url = tenant.api_url
    elif tenant.custom_domain:
        api_url = f"https://{tenant.custom_domain}/api/v1"
    elif tenant.subdomain:
        api_url = f"https://{tenant.subdomain}.tech-emp.com/api/v1"
    else:
        # Fallback para API Gateway multi-tenant - URL especifica por produto
        product_code = (tenant.product_code or "enterprise").lower()
        if product_code == "diario":
            api_url = "https://api.softwarecorp.com.br/api/gateway/diario"
        elif product_code == "condotech":
            api_url = "https://api.softwarecorp.com.br/api/gateway/condotech"
        else:
            # Enterprise e outros usam o gateway generico
            api_url = "https://api.softwarecorp.com.br/api/gateway"

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


class ChangePasswordRequest(BaseModel):
    """Request para troca de senha via JSON body"""
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_tenant_password(
    request: Request,
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Troca a senha do usuario no banco do tenant (isolado).
    Usa o token JWT para identificar tenant e email.
    Mantém a arquitetura multi-tenant com bancos separados.
    """
    # Extrai token do header Authorization
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticacao necessario"
        )

    token = auth_header.replace("Bearer ", "")

    # Decodifica token para obter tenant_code e email
    try:
        from jose import jwt
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        tenant_code = payload.get("tenant_code")
        email = payload.get("sub")  # email esta no campo 'sub'

        if not tenant_code or not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalido"
            )
    except Exception as e:
        logger.error(f"Erro ao decodificar token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido ou expirado"
        )

    # Busca tenant no License Server (banco central)
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
        data.current_password
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
            new_hash = hashlib.sha256(data.new_password.encode()).hexdigest()
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


# =====================================================
# RECUPERACAO DE SENHA
# =====================================================

class ForgotPasswordRequest(BaseModel):
    """Request para solicitar recuperacao de senha"""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Request para resetar senha com token"""
    token: str
    new_password: str


def generate_reset_token() -> str:
    """
    Gera um token seguro para recuperacao de senha.
    Usa secrets.token_urlsafe para gerar 32 bytes de entropia.
    """
    return secrets.token_urlsafe(32)


async def find_user_tenant(email: str, db: AsyncSession) -> tuple[Optional[object], Optional[dict]]:
    """
    Encontra o tenant e usuario pelo email.
    Busca primeiro pelo email principal do tenant, depois em todos os tenants ativos.

    Returns:
        (tenant, user_info) ou (None, None) se nao encontrado
    """
    email_lower = email.lower()

    # 1. Busca tenant pelo email principal
    result = await db.execute(
        select(Tenant).where(Tenant.email == email_lower)
    )
    tenant = result.scalar_one_or_none()

    if tenant and tenant.provisioned_at:
        # Verifica se usuario existe no banco do tenant
        try:
            conn = await asyncpg.connect(
                host=tenant.database_host or settings.POSTGRES_HOST,
                port=tenant.database_port or settings.POSTGRES_PORT,
                user=tenant.database_user,
                password=tenant.database_password,
                database=tenant.database_name
            )
            try:
                user = await conn.fetchrow("""
                    SELECT id, email, full_name
                    FROM users
                    WHERE email = $1 AND (deleted_at IS NULL OR deleted_at > CURRENT_TIMESTAMP)
                """, email_lower)
                if user:
                    return tenant, {"id": str(user['id']), "email": user['email'], "name": user['full_name']}
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"Erro ao buscar usuario no tenant principal: {e}")

    # 2. Busca usuario em todos os tenants ativos
    tenants_result = await db.execute(
        select(Tenant).where(
            Tenant.provisioned_at.isnot(None),
            Tenant.status.in_([TenantStatus.ACTIVE.value, TenantStatus.TRIAL.value])
        )
    )
    active_tenants = tenants_result.scalars().all()

    for t in active_tenants:
        try:
            conn = await asyncpg.connect(
                host=t.database_host or settings.POSTGRES_HOST,
                port=t.database_port or settings.POSTGRES_PORT,
                user=t.database_user,
                password=t.database_password,
                database=t.database_name
            )
            try:
                user = await conn.fetchrow("""
                    SELECT id, email, full_name
                    FROM users
                    WHERE email = $1 AND (deleted_at IS NULL OR deleted_at > CURRENT_TIMESTAMP)
                """, email_lower)
                if user:
                    return t, {"id": str(user['id']), "email": user['email'], "name": user['full_name']}
            finally:
                await conn.close()
        except Exception:
            continue

    return None, None


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(
    request_data: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Solicita recuperacao de senha.

    1. Busca usuario pelo email em todos os tenants
    2. Gera token seguro com expiracao de 1 hora
    3. Salva token no banco do tenant
    4. Envia email com link de recuperacao

    SEGURANCA:
    - Rate limit de 3 requisicoes por minuto
    - Resposta generica para evitar enumeracao de emails
    - Token expira em 1 hora
    - Token e invalidado apos uso
    """
    email = request_data.email.lower()

    # Resposta generica para evitar enumeracao de usuarios
    generic_response = {
        "success": True,
        "message": "Se o email estiver cadastrado, voce recebera um link para recuperacao de senha."
    }

    # Busca tenant e usuario
    tenant, user_info = await find_user_tenant(email, db)

    if not tenant or not user_info:
        # Retorna mesma resposta para evitar enumeracao
        logger.info(f"Tentativa de recuperacao de senha para email nao encontrado: {email}")
        return generic_response

    # Gera token seguro
    reset_token = generate_reset_token()
    expires_at = datetime.utcnow() + timedelta(hours=1)

    # Salva token no banco do tenant
    try:
        conn = await asyncpg.connect(
            host=tenant.database_host or settings.POSTGRES_HOST,
            port=tenant.database_port or settings.POSTGRES_PORT,
            user=tenant.database_user,
            password=tenant.database_password,
            database=tenant.database_name
        )
        try:
            await conn.execute("""
                UPDATE users
                SET reset_token = $1, reset_token_expires_at = $2, updated_at = $3
                WHERE email = $4
            """, reset_token, expires_at, datetime.utcnow(), email)
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Erro ao salvar token de recuperacao: {e}")
        return generic_response

    # Monta URL de recuperacao
    # Em producao: https://www.tech-emp.com/reset-password?token=XXX
    # Em desenvolvimento: http://localhost:5173/reset-password?token=XXX
    base_url = settings.APP_URL or "https://www.tech-emp.com"
    reset_url = f"{base_url}/reset-password?token={reset_token}"

    # Envia email
    try:
        email_sent = email_service.send_password_reset_email(
            to_email=email,
            name=user_info.get('name') or email.split('@')[0],
            reset_url=reset_url
        )
        if not email_sent:
            logger.warning(f"Falha ao enviar email de recuperacao para: {email}")
    except Exception as e:
        logger.error(f"Erro ao enviar email de recuperacao: {e}")

    logger.info(f"Token de recuperacao gerado para: {email}")
    return generic_response


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(
    request_data: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Redefine a senha usando o token de recuperacao.

    1. Busca usuario pelo token em todos os tenants
    2. Verifica se token nao expirou
    3. Atualiza senha e invalida token

    SEGURANCA:
    - Rate limit de 5 requisicoes por minuto
    - Token e invalidado apos uso (one-time use)
    - Senha deve ter minimo 6 caracteres
    """
    token = request_data.token
    new_password = request_data.new_password

    # Valida nova senha
    if len(data.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A nova senha deve ter no minimo 6 caracteres"
        )

    # Busca usuario pelo token em todos os tenants
    found_tenant = None
    found_user_email = None

    tenants_result = await db.execute(
        select(Tenant).where(
            Tenant.provisioned_at.isnot(None),
            Tenant.status.in_([TenantStatus.ACTIVE.value, TenantStatus.TRIAL.value])
        )
    )
    active_tenants = tenants_result.scalars().all()

    for t in active_tenants:
        try:
            conn = await asyncpg.connect(
                host=t.database_host or settings.POSTGRES_HOST,
                port=t.database_port or settings.POSTGRES_PORT,
                user=t.database_user,
                password=t.database_password,
                database=t.database_name
            )
            try:
                user = await conn.fetchrow("""
                    SELECT email, reset_token_expires_at
                    FROM users
                    WHERE reset_token = $1 AND (deleted_at IS NULL OR deleted_at > CURRENT_TIMESTAMP)
                """, token)
                if user:
                    found_tenant = t
                    found_user_email = user['email']
                    expires_at = user['reset_token_expires_at']
                    break
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"Erro ao buscar token no tenant {t.tenant_code}: {e}")
            continue

    if not found_tenant or not found_user_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token invalido ou expirado. Solicite um novo link de recuperacao."
        )

    # Verifica expiracao
    if expires_at and datetime.utcnow() > expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token expirado. Solicite um novo link de recuperacao."
        )

    # Atualiza senha e invalida token
    try:
        conn = await asyncpg.connect(
            host=found_tenant.database_host or settings.POSTGRES_HOST,
            port=found_tenant.database_port or settings.POSTGRES_PORT,
            user=found_tenant.database_user,
            password=found_tenant.database_password,
            database=found_tenant.database_name
        )
        try:
            # Hash da nova senha (SHA256 para novos tenants)
            new_hash = hashlib.sha256(new_password.encode()).hexdigest()

            await conn.execute("""
                UPDATE users
                SET hashed_password = $1,
                    reset_token = NULL,
                    reset_token_expires_at = NULL,
                    must_change_password = FALSE,
                    updated_at = $2
                WHERE email = $3
            """, new_hash, datetime.utcnow(), found_user_email)
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Erro ao atualizar senha: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar senha. Tente novamente."
        )

    # Marca que senha foi trocada no tenant (se aplicavel)
    if not found_tenant.password_changed:
        found_tenant.password_changed = True
        found_tenant.activated_at = datetime.utcnow()
        await db.commit()

    logger.info(f"Senha redefinida com sucesso para: {found_user_email}")

    return {
        "success": True,
        "message": "Senha redefinida com sucesso! Voce ja pode fazer login."
    }


@router.get("/verify-reset-token/{token}")
async def verify_reset_token(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Verifica se um token de recuperacao e valido.
    Usado para validar o token antes de mostrar o formulario de nova senha.
    """
    # Busca usuario pelo token em todos os tenants
    tenants_result = await db.execute(
        select(Tenant).where(
            Tenant.provisioned_at.isnot(None),
            Tenant.status.in_([TenantStatus.ACTIVE.value, TenantStatus.TRIAL.value])
        )
    )
    active_tenants = tenants_result.scalars().all()

    for t in active_tenants:
        try:
            conn = await asyncpg.connect(
                host=t.database_host or settings.POSTGRES_HOST,
                port=t.database_port or settings.POSTGRES_PORT,
                user=t.database_user,
                password=t.database_password,
                database=t.database_name
            )
            try:
                user = await conn.fetchrow("""
                    SELECT email, reset_token_expires_at
                    FROM users
                    WHERE reset_token = $1 AND (deleted_at IS NULL OR deleted_at > CURRENT_TIMESTAMP)
                """, token)
                if user:
                    # Verifica expiracao
                    expires_at = user['reset_token_expires_at']
                    if expires_at and datetime.utcnow() > expires_at:
                        return {
                            "valid": False,
                            "message": "Token expirado. Solicite um novo link de recuperacao."
                        }
                    return {
                        "valid": True,
                        "email": user['email'],
                        "message": "Token valido"
                    }
            finally:
                await conn.close()
        except Exception:
            continue

    return {
        "valid": False,
        "message": "Token invalido ou expirado."
    }
