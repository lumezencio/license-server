"""
License Server - Client Model
Representa empresas/clientes que compram licenças
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import relationship

from app.database import Base


class Client(Base):
    """Modelo de Cliente (empresa que compra licença)"""
    __tablename__ = "clients"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Dados da empresa
    name = Column(String(255), nullable=False, index=True)
    document = Column(String(20), unique=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    phone = Column(String(20))
    contact_name = Column(String(255))

    # Endereço
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(2))
    country = Column(String(50), default="Brasil")

    # Controle
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    metadata_ = Column("metadata", JSON, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    licenses = relationship("License", back_populates="client", lazy="selectin")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "document": self.document,
            "email": self.email,
            "phone": self.phone,
            "contact_name": self.contact_name,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "is_active": self.is_active,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "licenses_count": len(self.licenses) if self.licenses else 0
        }
