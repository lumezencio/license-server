"""
License Server - Auth Schemas
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    is_superadmin: bool = False


class AdminUserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    is_active: bool
    is_superadmin: bool
    last_login_at: Optional[str]
    created_at: Optional[str]

    class Config:
        from_attributes = True
