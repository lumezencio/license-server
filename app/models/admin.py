"""
License Server - Admin User Model
Usuários administradores do sistema de licenças
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime

from app.database import Base


class AdminUser(Base):
    """Modelo de usuário admin"""
    __tablename__ = "admin_users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))

    is_active = Column(Boolean, default=True)
    is_superadmin = Column(Boolean, default=False)

    last_login_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "is_superadmin": self.is_superadmin,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
