"""
License Server - Payments API
Endpoints para integração com Mercado Pago

FLUXO DE PAGAMENTO:
1. Cliente escolhe plano no frontend
2. Frontend chama POST /payments/create-preference
3. Backend cria preferência no Mercado Pago
4. Frontend redireciona para checkout do MP ou exibe QR Code PIX
5. Cliente paga
6. Mercado Pago envia webhook para POST /payments/webhook
7. Backend atualiza trial_expires_at do tenant (SOMA dias)
8. Cliente tem acesso estendido automaticamente!
"""
import uuid
import logging
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel

# SDK do Mercado Pago
import mercadopago

from app.database import get_db
from app.models import Tenant, TenantStatus, SubscriptionPlan, PaymentTransaction, PaymentStatus
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Payments"])


# ============================================================
# SCHEMAS (Pydantic)
# ============================================================

class CreatePreferenceRequest(BaseModel):
    """Request para criar preferência de pagamento"""
    tenant_code: str
    plan_code: str


class CreatePreferenceResponse(BaseModel):
    """Response com dados do checkout"""
    preference_id: str
    init_point: str  # URL do checkout
    sandbox_init_point: str  # URL do checkout sandbox
    transaction_id: str  # ID da nossa transação


class PlanResponse(BaseModel):
    """Response com dados do plano"""
    id: str
    code: str
    name: str
    description: Optional[str]
    days: int
    price: float
    original_price: Optional[float]
    discount_percent: float
    is_featured: bool


class PaymentHistoryResponse(BaseModel):
    """Response com histórico de pagamentos"""
    id: str
    plan_name: Optional[str]
    amount: float
    days_purchased: int
    status: str
    payment_method: Optional[str]
    paid_at: Optional[str]
    created_at: str


# ============================================================
# INICIALIZAÇÃO DOS PLANOS
# ============================================================

# Planos pré-definidos conforme solicitado
DEFAULT_PLANS = [
    {"code": "plan_30", "name": "Plano 30 Dias", "days": 30, "price": 35.00, "original_price": 35.00, "discount_percent": 0, "sort_order": 1},
    {"code": "plan_60", "name": "Plano 60 Dias", "days": 60, "price": 65.00, "original_price": 70.00, "discount_percent": 7, "sort_order": 2},
    {"code": "plan_90", "name": "Plano 90 Dias", "days": 90, "price": 90.00, "original_price": 105.00, "discount_percent": 14, "sort_order": 3},
    {"code": "plan_120", "name": "Plano 120 Dias", "days": 120, "price": 112.00, "original_price": 140.00, "discount_percent": 20, "sort_order": 4, "is_featured": True},
    {"code": "plan_180", "name": "Plano 180 Dias", "days": 180, "price": 162.00, "original_price": 210.00, "discount_percent": 23, "sort_order": 5},
    {"code": "plan_360", "name": "Plano 360 Dias", "days": 360, "price": 300.00, "original_price": 420.00, "discount_percent": 29, "sort_order": 6},
]


async def ensure_plans_exist(db: AsyncSession):
    """Garante que os planos padrão existam no banco"""
    for plan_data in DEFAULT_PLANS:
        result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.code == plan_data["code"])
        )
        existing = result.scalar_one_or_none()

        if not existing:
            plan = SubscriptionPlan(
                code=plan_data["code"],
                name=plan_data["name"],
                description=f"Assinatura por {plan_data['days']} dias",
                days=plan_data["days"],
                price=plan_data["price"],
                original_price=plan_data.get("original_price"),
                discount_percent=plan_data.get("discount_percent", 0),
                is_featured=plan_data.get("is_featured", False),
                sort_order=plan_data.get("sort_order", 0),
                is_active=True
            )
            db.add(plan)
            logger.info(f"Plano {plan_data['code']} criado")

    await db.commit()


# ============================================================
# ENDPOINTS
# ============================================================

@router.get("/plans", response_model=List[PlanResponse])
async def list_plans(db: AsyncSession = Depends(get_db)):
    """
    Lista todos os planos de assinatura disponíveis.
    Retorna ordenado por sort_order.
    """
    # Garante que os planos existam
    await ensure_plans_exist(db)

    result = await db.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.is_active == True)
        .order_by(SubscriptionPlan.sort_order)
    )
    plans = result.scalars().all()

    return [
        PlanResponse(
            id=p.id,
            code=p.code,
            name=p.name,
            description=p.description,
            days=p.days,
            price=p.price,
            original_price=p.original_price,
            discount_percent=p.discount_percent or 0,
            is_featured=p.is_featured or False
        )
        for p in plans
    ]


@router.post("/create-preference", response_model=CreatePreferenceResponse)
async def create_preference(
    request: CreatePreferenceRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Cria uma preferência de pagamento no Mercado Pago.

    Retorna a URL do checkout para redirecionar o cliente.
    """
    # Verifica se o token está configurado
    if not settings.MP_ACCESS_TOKEN:
        logger.error("MP_ACCESS_TOKEN não configurado!")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuração de pagamento incompleta. Contate o suporte."
        )

    # Busca o tenant
    result = await db.execute(
        select(Tenant).where(Tenant.tenant_code == request.tenant_code)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant não encontrado"
        )

    # Busca o plano
    await ensure_plans_exist(db)

    result = await db.execute(
        select(SubscriptionPlan).where(
            SubscriptionPlan.code == request.plan_code,
            SubscriptionPlan.is_active == True
        )
    )
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plano não encontrado"
        )

    # Cria transação local
    transaction = PaymentTransaction(
        tenant_id=tenant.id,
        plan_id=plan.id,
        amount=plan.price,
        days_purchased=plan.days,
        status=PaymentStatus.PENDING.value
    )
    db.add(transaction)
    await db.flush()

    # Referência externa (para identificar no webhook)
    external_reference = f"{tenant.tenant_code}|{transaction.id}"
    transaction.mp_external_reference = external_reference

    # Inicializa SDK do Mercado Pago
    sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)

    # Cria a preferência
    preference_data = {
        "items": [
            {
                "id": plan.code,
                "title": f"Tech-EMP - {plan.name}",
                "description": f"Assinatura do sistema Tech-EMP por {plan.days} dias",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": float(plan.price)
            }
        ],
        "payer": {
            "email": tenant.email,
            "name": tenant.name
        },
        "external_reference": external_reference,
        "notification_url": f"{settings.APP_URL.replace('www.', 'license.')}/api/payments/webhook",
        "back_urls": {
            "success": f"{settings.APP_URL}/pagamento/sucesso?ref={transaction.id}",
            "failure": f"{settings.APP_URL}/pagamento/erro?ref={transaction.id}",
            "pending": f"{settings.APP_URL}/pagamento/pendente?ref={transaction.id}"
        },
        "auto_return": "approved",
        "statement_descriptor": "TECH-EMP",
        "expires": True,
        "expiration_date_from": datetime.utcnow().isoformat() + "Z",
        "expiration_date_to": (datetime.utcnow() + timedelta(hours=24)).isoformat() + "Z"
    }

    try:
        preference_response = sdk.preference().create(preference_data)

        if preference_response["status"] != 201:
            logger.error(f"Erro ao criar preferência: {preference_response}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao criar pagamento. Tente novamente."
            )

        preference = preference_response["response"]

        # Atualiza transação com dados do MP
        transaction.mp_preference_id = preference["id"]
        await db.commit()

        logger.info(f"Preferência criada: {preference['id']} para tenant {tenant.tenant_code}")

        return CreatePreferenceResponse(
            preference_id=preference["id"],
            init_point=preference["init_point"],
            sandbox_init_point=preference.get("sandbox_init_point", preference["init_point"]),
            transaction_id=transaction.id
        )

    except Exception as e:
        logger.error(f"Erro ao criar preferência no MP: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao processar pagamento: {str(e)}"
        )


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Webhook para receber notificações do Mercado Pago.

    Quando um pagamento é confirmado:
    1. Busca a transação pela referência externa
    2. Atualiza o status da transação
    3. SOMA os dias ao trial_expires_at do tenant
    4. Atualiza status do tenant para ACTIVE se necessário
    """
    try:
        body = await request.json()
        logger.info(f"Webhook recebido: {body}")

        # Tipo de notificação
        notification_type = body.get("type") or body.get("topic")

        # Ignora notificações que não são de pagamento
        if notification_type != "payment":
            logger.info(f"Ignorando notificação do tipo: {notification_type}")
            return {"status": "ignored", "type": notification_type}

        # ID do pagamento
        payment_id = None
        if "data" in body and "id" in body["data"]:
            payment_id = body["data"]["id"]
        elif "resource" in body:
            # Formato antigo
            payment_id = body["resource"].split("/")[-1]

        if not payment_id:
            logger.warning("Webhook sem payment_id")
            return {"status": "no_payment_id"}

        # Busca detalhes do pagamento na API do Mercado Pago
        sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)
        payment_response = sdk.payment().get(payment_id)

        if payment_response["status"] != 200:
            logger.error(f"Erro ao buscar pagamento {payment_id}: {payment_response}")
            return {"status": "error", "message": "Pagamento não encontrado no MP"}

        payment_data = payment_response["response"]
        logger.info(f"Dados do pagamento: status={payment_data.get('status')}, ref={payment_data.get('external_reference')}")

        # Extrai referência externa (tenant_code|transaction_id)
        external_reference = payment_data.get("external_reference", "")
        if not external_reference or "|" not in external_reference:
            logger.warning(f"external_reference inválido: {external_reference}")
            return {"status": "invalid_reference"}

        tenant_code, transaction_id = external_reference.split("|", 1)

        # Busca a transação
        result = await db.execute(
            select(PaymentTransaction).where(PaymentTransaction.id == transaction_id)
        )
        transaction = result.scalar_one_or_none()

        if not transaction:
            logger.warning(f"Transação não encontrada: {transaction_id}")
            return {"status": "transaction_not_found"}

        # Atualiza dados da transação
        mp_status = payment_data.get("status", "")
        transaction.mp_payment_id = str(payment_id)
        transaction.mp_status = mp_status
        transaction.mp_status_detail = payment_data.get("status_detail", "")
        transaction.payment_method = payment_data.get("payment_method_id", "")
        transaction.payer_email = payment_data.get("payer", {}).get("email", "")
        transaction.payer_id = str(payment_data.get("payer", {}).get("id", ""))
        transaction.webhook_data = payment_data

        # Mapeia status do MP para nosso status
        status_mapping = {
            "approved": PaymentStatus.APPROVED.value,
            "authorized": PaymentStatus.AUTHORIZED.value,
            "pending": PaymentStatus.PENDING.value,
            "in_process": PaymentStatus.IN_PROCESS.value,
            "in_mediation": PaymentStatus.IN_MEDIATION.value,
            "rejected": PaymentStatus.REJECTED.value,
            "cancelled": PaymentStatus.CANCELLED.value,
            "refunded": PaymentStatus.REFUNDED.value,
            "charged_back": PaymentStatus.CHARGED_BACK.value
        }
        transaction.status = status_mapping.get(mp_status, mp_status)

        # Se pagamento aprovado, estende o período do tenant
        if mp_status == "approved":
            # PROTEÇÃO: Só processa se ainda não foi processado (evita duplicação quando MP envia múltiplos webhooks)
            if transaction.paid_at is None:
                transaction.paid_at = datetime.utcnow()

                # Busca o tenant
                result = await db.execute(
                    select(Tenant).where(Tenant.id == transaction.tenant_id)
                )
                tenant = result.scalar_one_or_none()

                if tenant:
                    now = datetime.utcnow()
                    days_to_add = transaction.days_purchased

                    # LÓGICA DE SOMA: Se ainda tem dias restantes, soma. Senão, começa de hoje.
                    if tenant.trial_expires_at and tenant.trial_expires_at > now:
                        # Ainda tem tempo válido - SOMA
                        new_expires = tenant.trial_expires_at + timedelta(days=days_to_add)
                        transaction.period_start = tenant.trial_expires_at
                    else:
                        # Expirado ou nunca teve - começa de hoje
                        new_expires = now + timedelta(days=days_to_add)
                        transaction.period_start = now

                    transaction.period_end = new_expires
                    tenant.trial_expires_at = new_expires

                    # Se era trial, agora é cliente pagante
                    if tenant.is_trial:
                        tenant.is_trial = False
                        tenant.status = TenantStatus.ACTIVE.value

                    # SINCRONIZA tabela licenses (usada pelo LicenseBadge no frontend)
                    if tenant.client_id:
                        from app.models import License
                        license_result = await db.execute(
                            select(License).where(License.client_id == tenant.client_id)
                        )
                        license = license_result.scalar_one_or_none()
                        if license:
                            license.expires_at = new_expires
                            license.is_trial = False
                            license.plan = "premium"  # Atualiza plano para premium após pagamento
                            logger.info(f"License {license.license_key} sincronizada até {new_expires}, plan=premium")

                    logger.info(f"Tenant {tenant.tenant_code} - Período estendido até {new_expires}")

        await db.commit()
        logger.info(f"Transação {transaction_id} atualizada: status={transaction.status}")

        return {"status": "processed", "payment_status": mp_status}

    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        await db.rollback()
        # Retorna 200 para o MP não reenviar (mas loga o erro)
        return {"status": "error", "message": str(e)}


@router.get("/history/{tenant_code}", response_model=List[PaymentHistoryResponse])
async def get_payment_history(
    tenant_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retorna o histórico de pagamentos de um tenant.
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

    # Busca transações
    result = await db.execute(
        select(PaymentTransaction)
        .where(PaymentTransaction.tenant_id == tenant.id)
        .order_by(PaymentTransaction.created_at.desc())
    )
    transactions = result.scalars().all()

    return [
        PaymentHistoryResponse(
            id=t.id,
            plan_name=t.plan.name if t.plan else None,
            amount=t.amount,
            days_purchased=t.days_purchased,
            status=t.status,
            payment_method=t.payment_method,
            paid_at=t.paid_at.isoformat() if t.paid_at else None,
            created_at=t.created_at.isoformat() if t.created_at else ""
        )
        for t in transactions
    ]


@router.get("/status/{transaction_id}")
async def get_payment_status(
    transaction_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Verifica o status de um pagamento específico.
    Útil para polling após redirect do checkout.
    """
    result = await db.execute(
        select(PaymentTransaction).where(PaymentTransaction.id == transaction_id)
    )
    transaction = result.scalar_one_or_none()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transação não encontrada"
        )

    return {
        "id": transaction.id,
        "status": transaction.status,
        "mp_status": transaction.mp_status,
        "paid_at": transaction.paid_at.isoformat() if transaction.paid_at else None,
        "amount": transaction.amount,
        "days_purchased": transaction.days_purchased,
        "period_end": transaction.period_end.isoformat() if transaction.period_end else None
    }


@router.post("/simulate-approval/{transaction_id}")
async def simulate_payment_approval(
    transaction_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    [APENAS DESENVOLVIMENTO] Simula a aprovação de um pagamento.
    Em produção, remover este endpoint ou proteger com autenticação.

    Útil para testar o fluxo localmente, já que o webhook do MP
    não consegue acessar localhost.
    """
    if settings.ENVIRONMENT == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Endpoint disponível apenas em desenvolvimento"
        )

    # Busca a transação
    result = await db.execute(
        select(PaymentTransaction).where(PaymentTransaction.id == transaction_id)
    )
    transaction = result.scalar_one_or_none()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transação não encontrada"
        )

    # PROTEÇÃO: Verifica se já foi processado
    if transaction.paid_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pagamento já foi processado anteriormente"
        )

    # Simula aprovação
    transaction.status = PaymentStatus.APPROVED.value
    transaction.mp_status = "approved"
    transaction.mp_status_detail = "accredited"
    transaction.mp_payment_id = f"SIMULATED_{uuid.uuid4().hex[:8]}"
    transaction.paid_at = datetime.utcnow()

    # Busca o tenant e estende o período
    result = await db.execute(
        select(Tenant).where(Tenant.id == transaction.tenant_id)
    )
    tenant = result.scalar_one_or_none()

    if tenant:
        now = datetime.utcnow()
        days_to_add = transaction.days_purchased

        # LÓGICA DE SOMA
        if tenant.trial_expires_at and tenant.trial_expires_at > now:
            new_expires = tenant.trial_expires_at + timedelta(days=days_to_add)
            transaction.period_start = tenant.trial_expires_at
        else:
            new_expires = now + timedelta(days=days_to_add)
            transaction.period_start = now

        transaction.period_end = new_expires
        tenant.trial_expires_at = new_expires

        if tenant.is_trial:
            tenant.is_trial = False
            tenant.status = TenantStatus.ACTIVE.value

        # SINCRONIZA tabela licenses (usada pelo LicenseBadge no frontend)
        if tenant.client_id:
            from app.models import License
            license_result = await db.execute(
                select(License).where(License.client_id == tenant.client_id)
            )
            license = license_result.scalar_one_or_none()
            if license:
                license.expires_at = new_expires
                license.is_trial = False
                license.plan = "premium"  # Atualiza plano para premium após pagamento
                logger.info(f"[SIMULADO] License {license.license_key} sincronizada até {new_expires}, plan=premium")

        await db.commit()

        logger.info(f"[SIMULADO] Tenant {tenant.tenant_code} - Período estendido até {new_expires}")

        return {
            "status": "approved",
            "message": f"Pagamento simulado com sucesso!",
            "tenant_code": tenant.tenant_code,
            "days_added": days_to_add,
            "new_expiration": new_expires.isoformat(),
            "transaction_id": transaction_id
        }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Tenant não encontrado"
    )
