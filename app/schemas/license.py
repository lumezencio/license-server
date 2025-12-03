"""
License Server - License Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.license import LicensePlan, LicenseStatus


class LicenseCreate(BaseModel):
    client_id: str
    plan: str = LicensePlan.STARTER.value
    features: List[str] = []
    max_users: int = Field(5, ge=1, le=1000)
    max_customers: int = Field(100, ge=1, le=100000)
    max_products: int = Field(500, ge=1, le=100000)
    max_monthly_transactions: int = Field(1000, ge=1, le=1000000)
    expires_at: datetime
    is_trial: bool = False
    notes: Optional[str] = None


class LicenseUpdate(BaseModel):
    plan: Optional[str] = None
    features: Optional[List[str]] = None
    max_users: Optional[int] = Field(None, ge=1, le=1000)
    max_customers: Optional[int] = Field(None, ge=1, le=100000)
    max_products: Optional[int] = Field(None, ge=1, le=100000)
    max_monthly_transactions: Optional[int] = Field(None, ge=1, le=1000000)
    expires_at: Optional[datetime] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class LicenseResponse(BaseModel):
    id: str
    license_key: str
    client_id: str
    client_name: Optional[str]
    hardware_id: Optional[str]
    plan: str
    features: List[str]
    max_users: int
    max_customers: int
    max_products: int
    max_monthly_transactions: int
    issued_at: Optional[datetime]
    activated_at: Optional[datetime]
    expires_at: Optional[datetime]
    last_validated_at: Optional[datetime]
    status: str
    is_trial: bool
    is_valid: bool
    days_until_expiry: int
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class LicenseActivateRequest(BaseModel):
    """Request para ativar licença"""
    license_key: str = Field(..., pattern=r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$')
    hardware_id: str = Field(..., min_length=16, max_length=64)
    hardware_info: Optional[dict] = None
    app_version: Optional[str] = None


class LicenseValidateRequest(BaseModel):
    """Request para validar licença (heartbeat)"""
    license_key: str
    hardware_id: str
    current_users: Optional[int] = None
    current_customers: Optional[int] = None
    current_products: Optional[int] = None
    app_version: Optional[str] = None


class LicenseValidateResponse(BaseModel):
    """Response da validação"""
    valid: bool
    status: str
    message: str
    license_key: Optional[str] = None
    plan: Optional[str] = None
    features: Optional[List[str]] = None
    expires_at: Optional[datetime] = None
    days_until_expiry: Optional[int] = None
    limits: Optional[dict] = None
    signature: Optional[str] = None


class LicenseFileResponse(BaseModel):
    """Arquivo de licença para download"""
    license_key: str
    client_id: str
    client_name: str
    hardware_id: str
    plan: str
    features: List[str]
    max_users: int
    issued_at: str
    expires_at: str
    version: str
    signature: str
