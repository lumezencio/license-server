"""
License Server - Registration API
Endpoint público para auto-registro de tenants (trial)

VERSÃO 2.0 - Provisionamento SÍNCRONO com RETRY automático
- O cadastro só retorna sucesso após o banco estar 100% provisionado
- Sistema de retry automático (3 tentativas)
- Tratamento robusto de erros
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
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

# Host do banco de dados dos tenants (usa configuracao ou nome do container Docker)
TENANT_DATABASE_HOST = settings.POSTGRES_HOST or "db"

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
    admin_name: str
) -> tuple[bool, str]:
    """
    Executa o provisionamento com sistema de retry automático.

    Tenta até MAX_PROVISION_RETRIES vezes antes de desistir.
    Aguarda RETRY_DELAY_SECONDS entre tentativas.

    Returns:
        tuple[bool, str]: (sucesso, mensagem)
    """
    last_error = ""

    for attempt in range(1, MAX_PROVISION_RETRIES + 1):
        try:
            logger.info(f"[{tenant_code}] Tentativa {attempt}/{MAX_PROVISION_RETRIES} de provisionamento...")

            success, message = await provisioning_service.provision_tenant(
                tenant_code=tenant_code,
                database_name=database_name,
                database_user=database_user,
                database_password=database_password,
                admin_email=admin_email,
                admin_password=admin_password,
                admin_name=admin_name
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


@router.post("/trial", response_model=TenantRegisterResponse)
async def register_trial(
    request: TenantRegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Registra um novo tenant com licença trial de 30 dias.

    FLUXO COMPLETO E SÍNCRONO:
    1. Valida dados (email e documento únicos)
    2. Cria registros no banco (tenant, client, license)
    3. Provisiona banco de dados do tenant (COM RETRY AUTOMÁTICO)
    4. Atualiza status para TRIAL/ACTIVE
    5. Envia email de boas-vindas
    6. Retorna credenciais

    O usuário SÓ recebe sucesso quando TUDO estiver pronto!

    Login: email informado
    Senha inicial: CPF/CNPJ (apenas números)
    """

    logger.info(f"=== NOVO REGISTRO: {request.email} ({request.document}) ===")

    # 1. Verifica se email já está cadastrado
    result = await db.execute(
        select(Tenant).where(Tenant.email == request.email)
    )
    if result.scalar_one_or_none():
        logger.warning(f"Email já cadastrado: {request.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este e-mail já está cadastrado. Faça login ou recupere sua senha."
        )

    # 2. Verifica se documento já está cadastrado
    result = await db.execute(
        select(Tenant).where(Tenant.document == request.document)
    )
    if result.scalar_one_or_none():
        logger.warning(f"Documento já cadastrado: {request.document}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este CPF/CNPJ já está cadastrado. Faça login ou recupere sua senha."
        )

    # 3. Gera dados do tenant
    tenant_code = Tenant.generate_tenant_code(request.document)
    database_name = Tenant.generate_database_name(request.document)
    database_user = Tenant.generate_database_user(request.document)
    database_password = Tenant.generate_database_password()

    logger.info(f"Tenant code gerado: {tenant_code}")
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

    logger.info(f"Registros criados. Iniciando provisionamento do banco...")

    # 11. PROVISIONAMENTO SÍNCRONO COM RETRY
    provision_success, provision_message = await provision_with_retry(
        tenant_code=tenant_code,
        database_name=database_name,
        database_user=database_user,
        database_password=database_password,
        admin_email=request.email,
        admin_password=request.document,  # CPF/CNPJ como senha inicial
        admin_name=request.name
    )

    # 12. Atualiza status baseado no resultado do provisionamento
    if provision_success:
        tenant.status = TenantStatus.TRIAL.value
        tenant.provisioned_at = datetime.utcnow()
        tenant.activated_at = datetime.utcnow()

        license.status = LicenseStatus.ACTIVE.value
        license.activated_at = datetime.utcnow()

        await db.commit()
        logger.info(f"=== TENANT {tenant_code} PROVISIONADO COM SUCESSO! ===")
    else:
        # Marca como ERRO mas não impede o cadastro
        tenant.status = TenantStatus.ERROR.value
        tenant.notes = f"Erro no provisionamento: {provision_message}"
        await db.commit()

        logger.error(f"=== FALHA NO PROVISIONAMENTO DO TENANT {tenant_code} ===")
        logger.error(f"Erro: {provision_message}")

        # Retorna erro para o usuário
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar seu ambiente. Por favor, entre em contato com o suporte. Código: {tenant_code}"
        )

    # 13. Envia email de boas-vindas (não bloqueia em caso de erro)
    login_url = f"{settings.LOGIN_URL}?tenant={tenant_code}"
    email_sent = send_welcome_email_safe(
        to_email=request.email,
        name=request.name,
        license_key=license_key,
        tenant_code=tenant_code,
        password_hint=f"Seu CPF/CNPJ: {request.document}",
        trial_days=30,
        login_url=login_url
    )

    # 14. Retorna resposta com credenciais
    response_message = "Cadastro realizado com sucesso! "
    if email_sent:
        response_message += "Você receberá um e-mail com as instruções de acesso."
    else:
        response_message += "Anote suas credenciais: Login = seu email, Senha = seu CPF/CNPJ (apenas números)."

    logger.info(f"=== REGISTRO COMPLETO: {tenant_code} ===")

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

    # Tenta provisionar novamente
    provision_success, provision_message = await provision_with_retry(
        tenant_code=tenant.tenant_code,
        database_name=tenant.database_name,
        database_user=tenant.database_user,
        database_password=tenant.database_password,
        admin_email=tenant.email,
        admin_password=tenant.document,
        admin_name=tenant.name
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
