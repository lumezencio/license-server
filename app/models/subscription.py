"""
License Server - Subscription Models
Modelos para planos de assinatura e transações de pagamento
"""
import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, Float, ForeignKey
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import relationship
from decimal import Decimal

from app.database import Base


class PaymentStatus(str, Enum):
    """Status do pagamento"""
    PENDING = "pending"           # Aguardando pagamento
    APPROVED = "approved"         # Pagamento aprovado
    AUTHORIZED = "authorized"     # Autorizado (cartão)
    IN_PROCESS = "in_process"     # Em processamento
    IN_MEDIATION = "in_mediation" # Em mediação
    REJECTED = "rejected"         # Rejeitado
    CANCELLED = "cancelled"       # Cancelado
    REFUNDED = "refunded"         # Reembolsado
    CHARGED_BACK = "charged_back" # Chargeback


class PaymentMethod(str, Enum):
    """Método de pagamento"""
    PIX = "pix"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    BOLETO = "boleto"
    ACCOUNT_MONEY = "account_money"  # Saldo Mercado Pago


class SubscriptionPlan(Base):
    """
    Modelo de Plano de Assinatura
    Define os planos disponíveis para compra
    """
    __tablename__ = "subscription_plans"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Identificador único do plano (usado em URLs e referências)
    code = Column(String(50), unique=True, nullable=False, index=True)

    # Informações do plano
    name = Column(String(100), nullable=False)  # Ex: "Plano 30 Dias"
    description = Column(Text)  # Descrição detalhada

    # Período e preço
    days = Column(Integer, nullable=False)  # Quantidade de dias
    price = Column(Float, nullable=False)   # Preço em reais (R$)

    # Desconto (para mostrar economia)
    original_price = Column(Float)  # Preço sem desconto (para mostrar economia)
    discount_percent = Column(Float, default=0)  # Percentual de desconto

    # Controle
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)  # Plano em destaque
    sort_order = Column(Integer, default=0)  # Ordem de exibição

    # Metadados
    metadata_ = Column("metadata", JSON, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "days": self.days,
            "price": self.price,
            "original_price": self.original_price,
            "discount_percent": self.discount_percent,
            "is_active": self.is_active,
            "is_featured": self.is_featured,
            "sort_order": self.sort_order
        }


class PaymentTransaction(Base):
    """
    Modelo de Transação de Pagamento
    Registra todas as transações de pagamento realizadas
    """
    __tablename__ = "payment_transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Referência ao tenant que está pagando
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="payment_transactions")

    # Referência ao plano comprado
    plan_id = Column(String(36), ForeignKey("subscription_plans.id"), nullable=False)
    plan = relationship("SubscriptionPlan")

    # Dados do pagamento
    amount = Column(Float, nullable=False)  # Valor pago
    days_purchased = Column(Integer, nullable=False)  # Dias comprados

    # Status
    status = Column(String(30), default=PaymentStatus.PENDING.value, index=True)
    payment_method = Column(String(30))  # pix, credit_card, boleto, etc

    # Dados do Mercado Pago
    mp_payment_id = Column(String(50), unique=True, index=True)  # ID do pagamento no MP
    mp_preference_id = Column(String(100))  # ID da preferência no MP
    mp_external_reference = Column(String(100), index=True)  # Referência externa (nosso ID)
    mp_status = Column(String(30))  # Status retornado pelo MP
    mp_status_detail = Column(String(100))  # Detalhe do status

    # Dados do pagador (do MP)
    payer_email = Column(String(255))
    payer_id = Column(String(50))

    # Datas importantes
    expires_at = Column(DateTime)  # Data de expiração do pagamento (PIX/Boleto)
    paid_at = Column(DateTime)  # Data que foi pago

    # Período adicionado ao tenant
    period_start = Column(DateTime)  # Início do período (data anterior + 1 dia ou hoje)
    period_end = Column(DateTime)  # Fim do período (start + days)

    # Informações extras
    notes = Column(Text)
    error_message = Column(Text)  # Mensagem de erro se houver
    webhook_data = Column(JSON)  # Dados brutos recebidos do webhook

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "plan_id": self.plan_id,
            "plan_name": self.plan.name if self.plan else None,
            "amount": self.amount,
            "days_purchased": self.days_purchased,
            "status": self.status,
            "payment_method": self.payment_method,
            "mp_payment_id": self.mp_payment_id,
            "mp_status": self.mp_status,
            "payer_email": self.payer_email,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
