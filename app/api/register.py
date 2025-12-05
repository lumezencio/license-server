"""
License Server - Registration API
Endpoint público para auto-registro de tenants (trial)
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import hashlib

from app.database import get_db
from app.models import Client, License, Tenant, TenantStatus, LicenseStatus
from app.schemas import (
    TenantRegisterRequest,
    TenantRegisterResponse,
    TenantResponse
)
from app.core import generate_license_key, email_service, settings

# Limites do plano trial
TRIAL_LIMITS = {
    'max_users': 1,
    'max_customers': 50,
    'max_products': 100,
    'max_monthly_transactions': 500,
    'features': ['basic_reports'],
}

router = APIRouter(prefix="/register", tags=["Registration"])


@router.post("/trial", response_model=TenantRegisterResponse)
async def register_trial(
    request: TenantRegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Registra um novo tenant com licença trial de 30 dias.

    - Cria registro do tenant
    - Cria cliente associado
    - Gera licença trial
    - Prepara credenciais de acesso

    Login: email informado
    Senha inicial: CPF/CNPJ (apenas números)
    """

    # 1. Verifica se email já está cadastrado
    result = await db.execute(
        select(Tenant).where(Tenant.email == request.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este e-mail já está cadastrado. Faça login ou recupere sua senha."
        )

    # 2. Verifica se documento já está cadastrado
    result = await db.execute(
        select(Tenant).where(Tenant.document == request.document)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este CPF/CNPJ já está cadastrado. Faça login ou recupere sua senha."
        )

    # 3. Gera dados do tenant
    tenant_code = Tenant.generate_tenant_code(request.document)
    database_name = Tenant.generate_database_name(request.document)
    database_user = Tenant.generate_database_user(request.document)
    database_password = Tenant.generate_database_password()

    # Hash da senha inicial (CPF/CNPJ)
    initial_password_hash = hashlib.sha256(request.document.encode()).hexdigest()

    # 4. Calcula data de expiração do trial (30 dias)
    trial_expires_at = datetime.utcnow() + timedelta(days=30)

    # 5. Cria o tenant
    tenant = Tenant(
        tenant_code=tenant_code,
        name=request.name,
        trade_name=request.company_name,
        document=request.document,
        email=request.email,
        phone=request.phone,
        database_name=database_name,
        database_user=database_user,
        database_password=database_password,
        initial_password_hash=initial_password_hash,
        status=TenantStatus.PENDING.value,
        is_trial=True,
        trial_days=30,
        trial_expires_at=trial_expires_at,
        registered_at=datetime.utcnow()
    )

    db.add(tenant)
    await db.flush()  # Para obter o ID antes do commit

    # 6. Cria o cliente no sistema de licenças
    # Usa o nome fantasia se disponível, senão o nome/razão social
    client_name = request.company_name if request.company_name else request.name
    client = Client(
        name=client_name,
        email=request.email,
        document=request.document,
        phone=request.phone,
        contact_name=request.name,  # Nome do responsável
        is_active=True,
        notes=f"Auto-registro trial - Tenant: {tenant_code}"
    )

    db.add(client)
    await db.flush()

    # 7. Vincula tenant ao client
    tenant.client_id = client.id

    # 8. Gera chave de licença única
    license_key = generate_license_key()

    # Garante unicidade da chave
    while True:
        result = await db.execute(
            select(License).where(License.license_key == license_key)
        )
        if not result.scalar_one_or_none():
            break
        license_key = generate_license_key()

    # 9. Cria a licença trial
    license = License(
        license_key=license_key,
        client_id=client.id,
        plan="trial",
        features=TRIAL_LIMITS['features'],
        max_users=TRIAL_LIMITS['max_users'],
        max_customers=TRIAL_LIMITS['max_customers'],
        max_products=TRIAL_LIMITS['max_products'],
        max_monthly_transactions=TRIAL_LIMITS['max_monthly_transactions'],
        expires_at=trial_expires_at,
        is_trial=True,
        status=LicenseStatus.PENDING.value,
        notes=f"Licença trial auto-gerada - Tenant: {tenant_code}"
    )

    db.add(license)

    # 10. Commit de tudo
    await db.commit()
    await db.refresh(tenant)

    # 11. Envia email de boas-vindas com credenciais
    login_url = f"{settings.LOGIN_URL}?tenant={tenant_code}"
    email_service.send_welcome_email(
        to_email=request.email,
        name=request.name,
        license_key=license_key,
        tenant_code=tenant_code,
        password_hint=f"Seu CPF/CNPJ: {request.document}",
        trial_days=30,
        login_url=login_url
    )

    # 12. Retorna resposta com credenciais
    return TenantRegisterResponse(
        success=True,
        message="Cadastro realizado com sucesso! Você receberá um e-mail com as instruções de acesso.",
        tenant_id=tenant.id,
        license_key=license_key,
        trial_days=30,
        trial_expires_at=trial_expires_at,
        login_email=request.email,
        login_password_hint="Sua senha inicial é o seu CPF/CNPJ (apenas números)",
        activation_url=login_url
    )


@router.get("/check-email/{email}")
async def check_email_available(
    email: str,
    db: AsyncSession = Depends(get_db)
):
    """Verifica se um e-mail está disponível para cadastro"""
    result = await db.execute(
        select(Tenant).where(Tenant.email == email)
    )
    exists = result.scalar_one_or_none() is not None

    return {
        "email": email,
        "available": not exists,
        "message": "E-mail disponível" if not exists else "E-mail já cadastrado"
    }


@router.get("/check-document/{document}")
async def check_document_available(
    document: str,
    db: AsyncSession = Depends(get_db)
):
    """Verifica se um CPF/CNPJ está disponível para cadastro"""
    # Remove caracteres não numéricos
    import re
    numbers = re.sub(r'\D', '', document)

    result = await db.execute(
        select(Tenant).where(Tenant.document == numbers)
    )
    exists = result.scalar_one_or_none() is not None

    return {
        "document": numbers,
        "available": not exists,
        "message": "Documento disponível" if not exists else "Documento já cadastrado"
    }


@router.get("/tenant/{tenant_code}", response_model=TenantResponse)
async def get_tenant_info(
    tenant_code: str,
    db: AsyncSession = Depends(get_db)
):
    """Retorna informações públicas do tenant (para página de login)"""
    result = await db.execute(
        select(Tenant).where(Tenant.tenant_code == tenant_code)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant não encontrado"
        )

    return TenantResponse(
        id=tenant.id,
        tenant_code=tenant.tenant_code,
        name=tenant.name,
        trade_name=tenant.trade_name,
        document=tenant.document,
        email=tenant.email,
        phone=tenant.phone,
        subdomain=tenant.subdomain,
        status=tenant.status,
        is_trial=tenant.is_trial,
        trial_days=tenant.trial_days,
        password_changed=tenant.password_changed,
        registered_at=tenant.registered_at,
        provisioned_at=tenant.provisioned_at,
        activated_at=tenant.activated_at,
        trial_expires_at=tenant.trial_expires_at,
        is_trial_valid=tenant.is_trial_valid(),
        client_id=tenant.client_id
    )
