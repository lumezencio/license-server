"""
License Server - Client Schemas
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class ClientCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    document: Optional[str] = Field(None, max_length=20)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    contact_name: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=2)
    country: str = "Brasil"
    notes: Optional[str] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    document: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    contact_name: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=2)
    country: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class ClientResponse(BaseModel):
    id: str
    name: str
    document: Optional[str] = None
    email: str
    phone: Optional[str] = None
    contact_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "Brasil"
    is_active: bool = True
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    licenses_count: int = 0

    class Config:
        from_attributes = True
