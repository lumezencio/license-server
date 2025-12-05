"""
License Server - Tenant Schemas
Schemas para o sistema de multi-tenant
"""
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional
from datetime import datetime
import re


class TenantRegisterRequest(BaseModel):
    """Request para registro de novo tenant (trial)"""
    name: str = Field(..., min_length=3, max_length=255, description="Nome completo ou razão social")
    email: EmailStr = Field(..., description="E-mail do responsável")
    document: str = Field(..., description="CPF ou CNPJ (apenas números)")
    phone: str = Field(..., description="Telefone (apenas números)")
    company_name: Optional[str] = Field(None, max_length=255, description="Nome fantasia")

    @field_validator('document')
    @classmethod
    def validate_document(cls, v):
        # Remove caracteres não numéricos
        numbers = re.sub(r'\D', '', v)

        if len(numbers) == 11:
            # Validação de CPF
            if not cls._validate_cpf(numbers):
                raise ValueError('CPF inválido')
        elif len(numbers) == 14:
            # Validação de CNPJ
            if not cls._validate_cnpj(numbers):
                raise ValueError('CNPJ inválido')
        else:
            raise ValueError('Documento deve ter 11 dígitos (CPF) ou 14 dígitos (CNPJ)')

        return numbers

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        numbers = re.sub(r'\D', '', v)
        if len(numbers) < 10 or len(numbers) > 11:
            raise ValueError('Telefone deve ter 10 ou 11 dígitos')
        return numbers

    @staticmethod
    def _validate_cpf(cpf: str) -> bool:
        """Valida CPF"""
        if len(cpf) != 11 or cpf == cpf[0] * 11:
            return False

        def calc_digit(cpf, factor):
            total = sum(int(digit) * (factor - i) for i, digit in enumerate(cpf[:factor - 1]))
            remainder = total % 11
            return 0 if remainder < 2 else 11 - remainder

        return calc_digit(cpf, 10) == int(cpf[9]) and calc_digit(cpf, 11) == int(cpf[10])

    @staticmethod
    def _validate_cnpj(cnpj: str) -> bool:
        """Valida CNPJ"""
        if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
            return False

        def calc_digit(cnpj, weights):
            total = sum(int(digit) * weight for digit, weight in zip(cnpj, weights))
            remainder = total % 11
            return 0 if remainder < 2 else 11 - remainder

        weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

        return (calc_digit(cnpj, weights1) == int(cnpj[12]) and
                calc_digit(cnpj, weights2) == int(cnpj[13]))


class TenantRegisterResponse(BaseModel):
    """Response do registro de tenant"""
    success: bool
    message: str
    tenant_id: Optional[str] = None
    license_key: Optional[str] = None
    trial_days: int = 30
    trial_expires_at: Optional[datetime] = None
    login_email: Optional[str] = None
    login_password_hint: Optional[str] = None  # Dica: "Seu CPF/CNPJ"
    activation_url: Optional[str] = None


class TenantResponse(BaseModel):
    """Response com dados do tenant"""
    id: str
    tenant_code: str
    name: str
    trade_name: Optional[str] = None
    document: str
    email: str
    phone: Optional[str] = None
    subdomain: Optional[str] = None
    status: str
    is_trial: bool
    trial_days: int
    password_changed: bool
    registered_at: Optional[datetime] = None
    provisioned_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    trial_expires_at: Optional[datetime] = None
    is_trial_valid: bool
    client_id: Optional[str] = None

    class Config:
        from_attributes = True


class TenantActivateRequest(BaseModel):
    """Request para ativar tenant com license key"""
    license_key: str = Field(..., pattern=r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$')
    hardware_id: str = Field(..., min_length=16, max_length=64)


class TenantLoginRequest(BaseModel):
    """Request para login do tenant"""
    email: EmailStr
    password: str = Field(..., min_length=1)


class TenantLoginResponse(BaseModel):
    """Response do login do tenant"""
    success: bool
    message: str
    tenant_id: Optional[str] = None
    tenant_code: Optional[str] = None
    database_url: Optional[str] = None
    redirect_url: Optional[str] = None
    access_token: Optional[str] = None
    is_first_access: bool = False
    must_change_password: bool = False


class TenantDatabaseInfo(BaseModel):
    """Informações do banco de dados do tenant (uso interno)"""
    database_name: str
    database_host: str
    database_port: int
    database_user: str
    database_url: str
