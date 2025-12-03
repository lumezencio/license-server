"""
License Server - License Model
Modelo principal de licenças com suporte a planos e features
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, ForeignKey, Enum
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class LicensePlan(str, enum.Enum):
    """Planos disponíveis"""
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    UNLIMITED = "unlimited"


class LicenseStatus(str, enum.Enum):
    """Status da licença"""
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class License(Base):
    """Modelo de Licença"""
    __tablename__ = "licenses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Chave de licença (XXXX-XXXX-XXXX-XXXX)
    license_key = Column(String(19), unique=True, nullable=False, index=True)

    # Cliente
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)
    client = relationship("Client", back_populates="licenses")

    # Hardware binding
    hardware_id = Column(String(64), index=True)
    hardware_info = Column(JSON, default=dict)

    # Plano e features
    plan = Column(String(20), default=LicensePlan.STARTER.value)
    features = Column(JSON, default=list)

    # Limites
    max_users = Column(Integer, default=5)
    max_customers = Column(Integer, default=100)
    max_products = Column(Integer, default=500)
    max_monthly_transactions = Column(Integer, default=1000)

    # Datas
    issued_at = Column(DateTime, default=datetime.utcnow)
    activated_at = Column(DateTime)
    expires_at = Column(DateTime, nullable=False)
    last_validated_at = Column(DateTime)
    last_heartbeat_at = Column(DateTime)

    # Status
    status = Column(String(20), default=LicenseStatus.PENDING.value, index=True)
    is_trial = Column(Boolean, default=False)

    # Assinatura RSA
    signature = Column(Text)

    # Metadados
    notes = Column(Text)
    metadata_ = Column("metadata", JSON, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Histórico de validações
    validations = relationship("LicenseValidation", back_populates="license", lazy="selectin")

    def is_valid(self) -> bool:
        """Verifica se licença está válida"""
        if self.status != LicenseStatus.ACTIVE.value:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True

    def days_until_expiry(self) -> int:
        """Dias até expirar"""
        if not self.expires_at:
            return 999
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)

    def to_dict(self, include_signature: bool = False):
        data = {
            "id": self.id,
            "license_key": self.license_key,
            "client_id": self.client_id,
            "client_name": self.client.name if self.client else None,
            "hardware_id": self.hardware_id,
            "plan": self.plan,
            "features": self.features or [],
            "max_users": self.max_users,
            "max_customers": self.max_customers,
            "max_products": self.max_products,
            "max_monthly_transactions": self.max_monthly_transactions,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_validated_at": self.last_validated_at.isoformat() if self.last_validated_at else None,
            "status": self.status,
            "is_trial": self.is_trial,
            "is_valid": self.is_valid(),
            "days_until_expiry": self.days_until_expiry(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_signature:
            data["signature"] = self.signature
        return data

    def to_license_file(self) -> dict:
        """Gera dados para arquivo de licença (distribuído ao cliente)"""
        return {
            "license_key": self.license_key,
            "client_id": self.client_id,
            "client_name": self.client.name if self.client else "",
            "hardware_id": self.hardware_id or "",
            "plan": self.plan,
            "features": self.features or [],
            "max_users": self.max_users,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "version": "1.0",
            "signature": self.signature
        }


class LicenseValidation(Base):
    """Histórico de validações de licença"""
    __tablename__ = "license_validations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    license_id = Column(String(36), ForeignKey("licenses.id"), nullable=False)
    license = relationship("License", back_populates="validations")

    # Info da validação
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    hardware_id = Column(String(64))
    validation_type = Column(String(20))  # activation, heartbeat, check

    # Resultado
    success = Column(Boolean, default=True)
    error_message = Column(Text)

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "license_id": self.license_id,
            "ip_address": self.ip_address,
            "validation_type": self.validation_type,
            "success": self.success,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
