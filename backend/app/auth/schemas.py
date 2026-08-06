"""Cópia de fv-laticinios/backend/app/auth/schemas.py.

Única divergência: `UserResponse.profile` foi removido, porque o `User` deste app
não tem a coluna `profile` (ver seção 10 do PLANO_APP_ESTOQUE_PROMOTOR.md).
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    email: str
    full_name: Optional[str]
    phone: Optional[str] = None
    role: str
    is_active: bool
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=30)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class UserPreferences(BaseModel):
    email_notifications: bool = True
    dark_mode: bool = False
    expiration_alerts: bool = True


class AvatarRequest(BaseModel):
    avatar_url: Optional[str] = Field(default=None, max_length=500000)
