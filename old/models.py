from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class UserCreate(BaseModel):
    """新規登録用のユーザーデータ"""
    email: str
    password: str

class UserLogin(BaseModel):
    """ログイン用のユーザーデータ"""
    email: str
    password: str

class UserResponse(BaseModel):
    """ユーザー情報レスポンス"""
    user_id: int
    email: str
    created_at: datetime
    last_login: Optional[datetime] = None

class SessionResponse(BaseModel):
    """セッション情報レスポンス"""
    session_id: str
    user_id: int
    expires_at: datetime
    is_active: bool

class AuthResponse(BaseModel):
    """認証レスポンス"""
    message: str
    user: Optional[UserResponse] = None

class ErrorResponse(BaseModel):
    """エラーレスポンス"""
    message: str