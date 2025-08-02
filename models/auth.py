# 認証関連のPydanticモデル
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class UserCreate(BaseModel):
    """新規ユーザー登録用モデル"""
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    """ログイン用モデル"""
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    """ユーザー情報レスポンスモデル"""
    user_id: int
    email: str
    created_at: datetime
    last_login: Optional[datetime] = None

class SessionResponse(BaseModel):
    """セッション情報レスポンスモデル"""
    session_id: str
    user_id: int
    expires_at: datetime
    is_active: bool

class AuthResponse(BaseModel):
    """認証レスポンスモデル"""
    message: str
    user: Optional[UserResponse] = None

class ErrorResponse(BaseModel):
    """エラーレスポンスモデル"""
    message: str
    error_code: Optional[str] = None