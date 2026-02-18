"""
License Server - Tenant Model
Representa um tenant (cliente) no sistema multi-tenant
Gerencia informações de banco de dados e provisionamento
"""
import uuid
import secrets
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, Enum as SQLEnum, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import relationship

from app.database import Base


class TenantStatus(str, Enum):
    """Status do tenant"""
    PENDING = "pending"           # Aguardando provisionamento
    PROVISIONING = "provisioning" # Em processo de criação
    ACTIVE = "active"             # Ativo e funcionando
    SUSPENDED = "suspended"       # Suspenso por falta de pagamento
    TRIAL = "trial"               # Em período de teste
    TRIAL_EXPIRED = "trial_expired"  # Trial expirado
    CANCELLED = "cancelled"       # Cancelado
    ERROR = "error"               # Erro no provisionamento


class Tenant(Base):
    """
    Modelo de Tenant - representa uma instância do sistema para um cliente.
    Cada tenant tem seu próprio banco de dados isolado.
    """
    __tablename__ = "tenants"
    __table_args__ = (
        # Constraints compostas: mesmo cliente pode estar em múltiplos produtos
        UniqueConstraint('tenant_code', 'product_code', name='uq_tenants_tenant_code_product'),
        UniqueConstraint('document', 'product_code', name='uq_tenants_document_product'),
        UniqueConstraint('email', 'product_code', name='uq_tenants_email_product'),
        UniqueConstraint('database_name', 'product_code', name='uq_tenants_database_name_product'),
        UniqueConstraint('subdomain', 'product_code', name='uq_tenants_subdomain_product'),
        # Indexes simples para performance de busca
        Index('ix_tenants_document', 'document'),
        Index('ix_tenants_email', 'email'),
        Index('ix_tenants_tenant_code', 'tenant_code'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Identificador único do tenant (CPF/CNPJ, único por produto)
    tenant_code = Column(String(100), nullable=False)

    # Dados do responsável/empresa
    name = Column(String(255), nullable=False)  # Nome completo ou razão social
    trade_name = Column(String(255))  # Nome fantasia
    document = Column(String(20), nullable=False)  # CPF ou CNPJ
    email = Column(String(255), nullable=False)
    phone = Column(String(20))

    # Produto/Sistema (enterprise, diario, botwhatsapp, condotech)
    product_code = Column(String(50), default="enterprise", nullable=False)

    # Configurações do banco de dados (único por produto)
    database_name = Column(String(100))  # Nome do banco: cliente_{document}
    database_host = Column(String(255), default="localhost")
    database_port = Column(Integer, default=5432)
    database_user = Column(String(100))
    database_password = Column(String(255))  # Criptografado

    # URL completa de conexão (gerada automaticamente)
    database_url = Column(Text)

    # Configurações de acesso
    subdomain = Column(String(50), unique=True)  # Opcional: empresa.tech-emp.com
    custom_domain = Column(String(255))  # Opcional: sistema.empresa.com
    api_url = Column(String(500))  # URL da API Gateway para este tenant

    # Credenciais de primeiro acesso (geradas no cadastro)
    initial_password_hash = Column(String(255))  # Hash do CPF/CNPJ
    password_changed = Column(Boolean, default=False)  # Se usuário já trocou a senha

    # Referência ao cliente no sistema de licenças
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=True)

    # Status e controle
    status = Column(String(20), default=TenantStatus.PENDING.value)
    is_trial = Column(Boolean, default=True)
    trial_days = Column(Integer, default=30)

    # Datas importantes
    registered_at = Column(DateTime, default=datetime.utcnow)  # Data do cadastro
    provisioned_at = Column(DateTime)  # Data que banco foi criado
    activated_at = Column(DateTime)  # Data que usuário ativou
    trial_expires_at = Column(DateTime)  # Data que trial expira
    suspended_at = Column(DateTime)  # Data que foi suspenso
    cancelled_at = Column(DateTime)  # Data que foi cancelado

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Metadados extras
    metadata_ = Column("metadata", JSON, default=dict)
    notes = Column(Text)

    # Relacionamentos
    client = relationship("Client", backref="tenant", uselist=False)

    @staticmethod
    def generate_tenant_code(document: str) -> str:
        """Gera código do tenant baseado no documento (CPF/CNPJ)"""
        # Remove caracteres não numéricos
        numbers = ''.join(filter(str.isdigit, document))
        return numbers

    @staticmethod
    def generate_database_name(document: str) -> str:
        """Gera nome do banco de dados baseado no documento"""
        numbers = ''.join(filter(str.isdigit, document))
        return f"cliente_{numbers}"

    @staticmethod
    def generate_database_user(document: str) -> str:
        """Gera usuário do banco de dados"""
        numbers = ''.join(filter(str.isdigit, document))
        return f"user_{numbers}"

    @staticmethod
    def generate_database_password() -> str:
        """Gera senha segura para o banco de dados"""
        return secrets.token_urlsafe(16)

    def get_database_url(self) -> str:
        """Retorna a URL de conexão do banco de dados"""
        if self.database_url:
            return self.database_url

        return (
            f"postgresql+asyncpg://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )

    def is_trial_valid(self) -> bool:
        """Verifica se o trial ainda é válido"""
        if not self.is_trial:
            return True  # Não é trial, está OK

        if not self.trial_expires_at:
            return False

        return datetime.utcnow() < self.trial_expires_at

    def to_dict(self, include_sensitive: bool = False):
        """Converte para dicionário"""
        data = {
            "id": self.id,
            "tenant_code": self.tenant_code,
            "name": self.name,
            "trade_name": self.trade_name,
            "document": self.document,
            "email": self.email,
            "phone": self.phone,
            "product_code": self.product_code,
            "subdomain": self.subdomain,
            "custom_domain": self.custom_domain,
            "status": self.status,
            "is_trial": self.is_trial,
            "trial_days": self.trial_days,
            "password_changed": self.password_changed,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
            "provisioned_at": self.provisioned_at.isoformat() if self.provisioned_at else None,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "trial_expires_at": self.trial_expires_at.isoformat() if self.trial_expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_trial_valid": self.is_trial_valid(),
            "client_id": self.client_id
        }

        if include_sensitive:
            data.update({
                "database_name": self.database_name,
                "database_host": self.database_host,
                "database_port": self.database_port,
                "database_user": self.database_user,
                "database_url": self.get_database_url()
            })

        return data
