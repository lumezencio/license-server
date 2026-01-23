"""
License Server - Registration API
Endpoint público para auto-registro de tenants (trial)

VERSÃO 3.0 - Provisionamento ASSÍNCRONO em background
- Registro retorna imediatamente após criar tenant
- Provisionamento ocorre em background (não bloqueia)
- Frontend pode verificar status via /register/status/{tenant_code}
- Evita timeout do Cloudflare (100s)
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import hashlib
import logging
import asyncio

from app.database import get_db, AsyncSessionLocal
from app.models import Client, License, Tenant, TenantStatus, LicenseStatus
from app.schemas import (
    TenantRegisterRequest,
    TenantRegisterResponse,
    TenantResponse
)
from app.core import generate_license_key, email_service, settings
from app.core.provisioning import provisioning_service, ProvisioningError
from app.core.error_notifier import send_error_notification
import traceback

logger = logging.getLogger(__name__)

# Limites do plano trial
TRIAL_LIMITS = {
    'max_users': 1,
    'max_customers': 50,
    'max_products': 100,
    'max_monthly_transactions': 500,
    'features': ['basic_reports'],
}

router = APIRouter(prefix="/register", tags=["Registration"])

# Host do banco de dados dos tenants
# IMPORTANTE: Em produção Docker, deve ser "license-db" (nome do container PostgreSQL)
# O settings.POSTGRES_HOST pode ser "localhost" em dev, mas em produção DEVE ser "license-db"
# Prioridade: variável de ambiente > fallback para container Docker
import os
TENANT_DATABASE_HOST = os.environ.get("POSTGRES_HOST") or settings.POSTGRES_HOST
# Se ainda for localhost (default do config), usa o nome do container Docker em produção
if TENANT_DATABASE_HOST == "localhost":
    TENANT_DATABASE_HOST = "license-db"

# Configurações de retry
MAX_PROVISION_RETRIES = 3
RETRY_DELAY_SECONDS = 2


async def provision_with_retry(
    tenant_code: str,
    database_name: str,
    database_user: str,
    database_password: str,
    admin_email: str,
    admin_password: str,
    admin_name: str,
    product_code: str = "enterprise"
) -> tuple[bool, str]:
    """
    Executa o provisionamento com sistema de retry automático.

    Tenta até MAX_PROVISION_RETRIES vezes antes de desistir.
    Aguarda RETRY_DELAY_SECONDS entre tentativas.

    Args:
        product_code: Código do produto (enterprise, condotech, etc.)

    Returns:
        tuple[bool, str]: (sucesso, mensagem)
    """
    last_error = ""

    for attempt in range(1, MAX_PROVISION_RETRIES + 1):
        try:
            logger.info(f"[{tenant_code}] Tentativa {attempt}/{MAX_PROVISION_RETRIES} de provisionamento ({product_code})...")

            success, message = await provisioning_service.provision_tenant(
                tenant_code=tenant_code,
                database_name=database_name,
                database_user=database_user,
                database_password=database_password,
                admin_email=admin_email,
                admin_password=admin_password,
                admin_name=admin_name,
                product_code=product_code
            )

            if success:
                logger.info(f"[{tenant_code}] Provisionamento concluído com sucesso na tentativa {attempt}!")
                return True, message
            else:
                last_error = message
                logger.warning(f"[{tenant_code}] Tentativa {attempt} falhou: {message}")

        except Exception as e:
            last_error = str(e)
            logger.error(f"[{tenant_code}] Erro na tentativa {attempt}: {e}")

        # Aguarda antes da próxima tentativa (exceto na última)
        if attempt < MAX_PROVISION_RETRIES:
            logger.info(f"[{tenant_code}] Aguardando {RETRY_DELAY_SECONDS}s antes da próxima tentativa...")
            await asyncio.sleep(RETRY_DELAY_SECONDS)

    logger.error(f"[{tenant_code}] Todas as {MAX_PROVISION_RETRIES} tentativas falharam!")
    return False, f"Falha após {MAX_PROVISION_RETRIES} tentativas: {last_error}"


def send_welcome_email_safe(
    to_email: str,
    name: str,
    license_key: str,
    tenant_code: str,
    password_hint: str,
    trial_days: int,
    login_url: str
) -> bool:
    """
    Envia email de boas-vindas de forma segura (não lança exceção).

    Returns:
        bool: True se enviou, False se falhou
    """
    try:
        email_service.send_welcome_email(
            to_email=to_email,
            name=name,
            license_key=license_key,
            tenant_code=tenant_code,
            password_hint=password_hint,
            trial_days=trial_days,
            login_url=login_url
        )
        logger.info(f"Email de boas-vindas enviado para {to_email}")
        return True
    except Exception as e:
        logger.warning(f"Falha ao enviar email para {to_email}: {e}")
        logger.warning("O cadastro foi realizado, mas o email não foi enviado. Configure SMTP_USER e SMTP_PASSWORD.")
        return False


async def background_provision_tenant(
    tenant_id: int,
    tenant_code: str,
    database_name: str,
    database_user: str,
    database_password: str,
    admin_email: str,
    admin_password: str,
    admin_name: str,
    product_code: str,
    license_key: str,
    client_id: int
):
    """
    Executa o provisionamento em background.
    Atualiza o status do tenant ao terminar.
    """
    logger.info(f"[BACKGROUND] Iniciando provisionamento do tenant {tenant_code}...")

    # Cria nova sessão para operação em background
    async with AsyncSessionLocal() as db:
        try:
            # Executa provisionamento com retry
            provision_success, provision_message = await provision_with_retry(
                tenant_code=tenant_code,
                database_name=database_name,
                database_user=database_user,
                database_password=database_password,
                admin_email=admin_email,
                admin_password=admin_password,
                admin_name=admin_name,
                product_code=product_code
            )

            # Busca tenant para atualizar
            result = await db.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            )
            tenant = result.scalar_one_or_none()

            if not tenant:
                logger.error(f"[BACKGROUND] Tenant {tenant_code} não encontrado!")
                return

            if provision_success:
                tenant.status = TenantStatus.TRIAL.value
                tenant.provisioned_at = datetime.utcnow()
                tenant.activated_at = datetime.utcnow()

                # Atualiza licença
                result = await db.execute(
                    select(License).where(License.client_id == client_id)
                )
                license = result.scalar_one_or_none()
                if license:
                    license.status = LicenseStatus.ACTIVE.value
                    license.activated_at = datetime.utcnow()

                await db.commit()
                logger.info(f"[BACKGROUND] === TENANT {tenant_code} PROVISIONADO COM SUCESSO! ===")

                # Envia email de boas-vindas (usa URL do produto correto)
                product_login_url = settings.get_product_url(product_code, "login_url")
                login_url = f"{product_login_url}?tenant={tenant_code}"
                send_welcome_email_safe(
                    to_email=admin_email,
                    name=admin_name,
                    license_key=license_key,
                    tenant_code=tenant_code,
                    password_hint=f"Seu CPF/CNPJ: {admin_password}",
                    trial_days=30,
                    login_url=login_url
                )
            else:
                tenant.status = TenantStatus.ERROR.value
                tenant.notes = f"Erro no provisionamento: {provision_message}"
                await db.commit()
                logger.error(f"[BACKGROUND] === FALHA NO PROVISIONAMENTO DO TENANT {tenant_code} ===")
                logger.error(f"[BACKGROUND] Erro: {provision_message}")
                # Notifica erro por email
                send_error_notification(
                    error_type="PROVISION_ERROR",
                    error_message=f"Falha no provisionamento do tenant {tenant_code}",
                    error_details=provision_message,
                    tenant_code=tenant_code,
                    user_email=admin_email,
                    endpoint="POST /register/trial (background)"
                )

        except Exception as e:
            logger.error(f"[BACKGROUND] Erro fatal no provisionamento de {tenant_code}: {e}")
            # Notifica erro fatal por email
            send_error_notification(
                error_type="PROVISION_FATAL_ERROR",
                error_message=f"Erro FATAL no provisionamento do tenant {tenant_code}",
                error_details=traceback.format_exc(),
                tenant_code=tenant_code,
                user_email=admin_email,
                endpoint="POST /register/trial (background)"
            )
            try:
                result = await db.execute(
                    select(Tenant).where(Tenant.id == tenant_id)
                )
                tenant = result.scalar_one_or_none()
                if tenant:
                    tenant.status = TenantStatus.ERROR.value
                    tenant.notes = f"Erro fatal: {str(e)}"
                    await db.commit()
            except:
                pass


@router.post("/trial", response_model=TenantRegisterResponse)
async def register_trial(
    request: TenantRegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Registra um novo tenant com licença trial de 30 dias.

    FLUXO ASSÍNCRONO (v3.0):
    1. Valida dados (email e documento únicos)
    2. Cria registros no banco (tenant, client, license)
    3. Retorna sucesso IMEDIATAMENTE
    4. Provisionamento ocorre em BACKGROUND
    5. Frontend verifica status via /register/status/{tenant_code}

    Evita timeout do Cloudflare (100s) fazendo provisionamento assíncrono.

    Login: email informado
    Senha inicial: CPF/CNPJ (apenas números)
    """

    logger.info(f"=== NOVO REGISTRO: {request.email} ({request.document}) - Produto: {request.product_code} ===")

    # 1. Verifica se email já está cadastrado PARA ESTE PRODUTO
    # Permite mesmo email em produtos diferentes (cada produto tem licença independente)
    result = await db.execute(
        select(Tenant).where(
            Tenant.email == request.email,
            Tenant.product_code == request.product_code
        )
    )
    if result.scalar_one_or_none():
        logger.warning(f"Email já cadastrado para {request.product_code}: {request.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Este e-mail já está cadastrado neste sistema. Faça login ou recupere sua senha."
        )

    # 2. Verifica se documento já está cadastrado PARA ESTE PRODUTO
    result = await db.execute(
        select(Tenant).where(
            Tenant.document == request.document,
            Tenant.product_code == request.product_code
        )
    )
    if result.scalar_one_or_none():
        logger.warning(f"Documento já cadastrado para {request.product_code}: {request.document}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Este CPF/CNPJ já está cadastrado neste sistema. Faça login ou recupere sua senha."
        )

    # 3. Gera dados do tenant
    # Para produtos diferentes do enterprise, adiciona sufixo para evitar conflitos
    product_suffix = "" if request.product_code == "enterprise" else f"_{request.product_code}"
    tenant_code = Tenant.generate_tenant_code(request.document) + product_suffix
    database_name = Tenant.generate_database_name(request.document) + product_suffix
    database_user = Tenant.generate_database_user(request.document) + product_suffix
    database_password = Tenant.generate_database_password()

    logger.info(f"Tenant code gerado: {tenant_code} (produto: {request.product_code})")
    logger.info(f"Database: {database_name}, User: {database_user}")

    # Hash da senha inicial (CPF/CNPJ)
    initial_password_hash = hashlib.sha256(request.document.encode()).hexdigest()

    # 4. Calcula data de expiração do trial (30 dias)
    trial_expires_at = datetime.utcnow() + timedelta(days=30)

    # 5. Cria o tenant com status PROVISIONING
    tenant = Tenant(
        tenant_code=tenant_code,
        name=request.name,
        trade_name=request.company_name,
        document=request.document,
        email=request.email,
        phone=request.phone,
        product_code=request.product_code,  # Código do produto (enterprise, condotech, etc.)
        database_name=database_name,
        database_user=database_user,
        database_password=database_password,
        database_host=TENANT_DATABASE_HOST,
        initial_password_hash=initial_password_hash,
        status=TenantStatus.PROVISIONING.value,  # Começa como PROVISIONING
        is_trial=True,
        trial_days=30,
        trial_expires_at=trial_expires_at,
        registered_at=datetime.utcnow()
    )

    db.add(tenant)
    await db.flush()

    # 6. Cria o cliente no sistema de licenças
    client_name = request.company_name if request.company_name else request.name
    client = Client(
        name=client_name,
        email=request.email,
        document=request.document,
        phone=request.phone,
        contact_name=request.name,
        is_active=True,
        notes=f"Auto-registro trial - Tenant: {tenant_code}"
    )

    db.add(client)
    await db.flush()

    # 7. Vincula tenant ao client
    tenant.client_id = client.id

    # 8. Gera chave de licença única
    license_key = generate_license_key()

    while True:
        result = await db.execute(
            select(License).where(License.license_key == license_key)
        )
        if not result.scalar_one_or_none():
            break
        license_key = generate_license_key()

    logger.info(f"License key gerada: {license_key}")

    # 9. Cria a licença trial com status PENDING
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

    # 10. Commit inicial (tenant em PROVISIONING)
    await db.commit()
    await db.refresh(tenant)
    await db.refresh(license)

    logger.info(f"Registros criados. Iniciando provisionamento em BACKGROUND...")

    # 11. PROVISIONAMENTO ASSÍNCRONO EM BACKGROUND (não bloqueia a resposta)
    # Usa asyncio.create_task para executar em paralelo
    asyncio.create_task(
        background_provision_tenant(
            tenant_id=tenant.id,
            tenant_code=tenant_code,
            database_name=database_name,
            database_user=database_user,
            database_password=database_password,
            admin_email=request.email,
            admin_password=request.document,
            admin_name=request.name,
            product_code=request.product_code,
            license_key=license_key,
            client_id=client.id
        )
    )

    # 12. Retorna sucesso IMEDIATAMENTE (provisionamento continua em background)
    # Usa URL do produto correto
    product_login_url = settings.get_product_url(request.product_code, "login_url")
    login_url = f"{product_login_url}?tenant={tenant_code}"
    response_message = (
        "Cadastro realizado com sucesso! "
        "Seu ambiente está sendo preparado (aguarde alguns segundos). "
        "Anote suas credenciais: Login = seu email, Senha = seu CPF/CNPJ (apenas números)."
    )

    logger.info(f"=== REGISTRO ACEITO: {tenant_code} (provisionamento em background) ===")

    return TenantRegisterResponse(
        success=True,
        message=response_message,
        tenant_id=tenant.id,
        license_key=license_key,
        trial_days=30,
        trial_expires_at=trial_expires_at,
        login_email=request.email,
        login_password_hint="Sua senha inicial é o seu CPF/CNPJ (apenas números)",
        activation_url=login_url
    )


@router.post("/retry-provision/{tenant_code}")
async def retry_provision(
    tenant_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Endpoint para retentar provisionamento de um tenant com erro.

    Útil para casos onde o provisionamento automático falhou.
    """
    # Busca o tenant
    result = await db.execute(
        select(Tenant).where(Tenant.tenant_code == tenant_code)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant não encontrado"
        )

    if tenant.status not in [TenantStatus.ERROR.value, TenantStatus.PENDING.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant não está em estado de erro. Status atual: {tenant.status}"
        )

    logger.info(f"=== RETRY PROVISIONAMENTO: {tenant_code} ===")

    # Atualiza status para PROVISIONING
    tenant.status = TenantStatus.PROVISIONING.value
    await db.commit()

    # Tenta provisionar novamente (usa product_code do tenant)
    provision_success, provision_message = await provision_with_retry(
        tenant_code=tenant.tenant_code,
        database_name=tenant.database_name,
        database_user=tenant.database_user,
        database_password=tenant.database_password,
        admin_email=tenant.email,
        admin_password=tenant.document,
        admin_name=tenant.name,
        product_code=tenant.product_code or "enterprise"
    )

    if provision_success:
        tenant.status = TenantStatus.TRIAL.value
        tenant.provisioned_at = datetime.utcnow()
        tenant.activated_at = datetime.utcnow()
        tenant.notes = f"Provisionado via retry em {datetime.utcnow()}"

        # Atualiza licença também
        result = await db.execute(
            select(License).where(License.client_id == tenant.client_id)
        )
        license = result.scalar_one_or_none()
        if license:
            license.status = LicenseStatus.ACTIVE.value
            license.activated_at = datetime.utcnow()

        await db.commit()

        return {
            "success": True,
            "message": f"Tenant {tenant_code} provisionado com sucesso!",
            "status": tenant.status
        }
    else:
        tenant.status = TenantStatus.ERROR.value
        tenant.notes = f"Retry falhou: {provision_message}"
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha no provisionamento: {provision_message}"
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

    # Busca a license_key do cliente associado
    license_key = None
    if tenant.client_id:
        result = await db.execute(
            select(License).where(License.client_id == tenant.client_id)
        )
        license = result.scalar_one_or_none()
        if license:
            license_key = license.license_key

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
        client_id=tenant.client_id,
        license_key=license_key
    )


@router.get("/status/{tenant_code}")
async def get_tenant_status(
    tenant_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retorna o status atual do tenant.
    Útil para verificar se o provisionamento foi concluído.
    """
    result = await db.execute(
        select(Tenant).where(Tenant.tenant_code == tenant_code)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant não encontrado"
        )

    return {
        "tenant_code": tenant.tenant_code,
        "status": tenant.status,
        "provisioned_at": tenant.provisioned_at,
        "activated_at": tenant.activated_at,
        "is_ready": tenant.status in [TenantStatus.TRIAL.value, TenantStatus.ACTIVE.value],
        "notes": tenant.notes
    }
