# 認証サービス
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, Cookie
from crud.users import UserCRUD, SessionCRUD
from database import db_connection
import logging

logger = logging.getLogger(__name__)

class AuthService:
    """認証関連のビジネスロジック"""
    
    def __init__(self):
        self.user_crud = UserCRUD(db_connection)
        self.session_crud = SessionCRUD(db_connection)
    
    async def register_user(self, email: str, password: str) -> Dict[str, Any]:
        """ユーザー登録"""
        # パスワードの基本検証
        if len(password) < 8:
            return {"success": False, "message": "パスワードは8文字以上で入力してください"}
        
        # ユーザー作成
        result = await self.user_crud.create_user(email, password)
        return result
    
    async def authenticate_user(self, email: str, password: str) -> Dict[str, Any]:
        """ユーザー認証"""
        result = await self.user_crud.authenticate_user(email, password)
        return result
    
    async def create_session(self, user_id: int) -> Optional[str]:
        """セッション作成"""
        session_id = await self.session_crud.create_session(user_id)
        return session_id
    
    async def validate_session(self, session_id: str) -> Optional[int]:
        """セッション検証"""
        user_id = await self.session_crud.validate_session(session_id)
        return user_id
    
    async def invalidate_session(self, session_id: str) -> bool:
        """セッション無効化"""
        return await self.session_crud.invalidate_session(session_id)
    
    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """ユーザー情報取得"""
        return await self.user_crud.get_user_by_id(user_id)
    
    async def cleanup_expired_sessions(self) -> int:
        """期限切れセッションのクリーンアップ"""
        return await self.session_crud.cleanup_expired_sessions()

# グローバルなAuthServiceインスタンス
auth_service = AuthService()

# FastAPI依存性注入用の関数
async def get_current_user(session_id: Optional[str] = Cookie(None)) -> int:
    """現在のユーザーを取得（セッション検証）"""
    if not session_id:
        raise HTTPException(status_code=401, detail="認証が必要です")
    
    user_id = await auth_service.validate_session(session_id)
    if not user_id:
        raise HTTPException(status_code=401, detail="無効なセッションです")
    
    return user_id

async def get_current_user_optional(session_id: Optional[str] = Cookie(None)) -> Optional[int]:
    """現在のユーザーを取得（オプショナル）"""
    if not session_id:
        return None
    
    user_id = await auth_service.validate_session(session_id)
    return user_id