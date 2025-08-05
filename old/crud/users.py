# ユーザー関連のCRUD操作
from typing import Optional, Dict, Any
import asyncpg
from passlib.context import CryptContext
from datetime import datetime, timedelta
import secrets
import logging

logger = logging.getLogger(__name__)

# パスワードハッシュ化のコンテキスト
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserCRUD:
    """ユーザー関連のデータベース操作クラス"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
    
    async def create_user(self, email: str, password: str) -> Dict[str, Any]:
        """新規ユーザーを作成"""
        try:
            # パスワードをハッシュ化
            hashed_password = pwd_context.hash(password)
            
            conn = await self.db_connection.get_async_connection()
            
            # ユーザーの重複チェック
            existing_user = await conn.fetchrow(
                "SELECT user_id FROM users WHERE email = $1", email
            )
            
            if existing_user:
                await conn.close()
                return {"success": False, "message": "このメールアドレスは既に登録されています"}
            
            # 新規ユーザーを挿入
            user_id = await conn.fetchval(
                """
                INSERT INTO users (email, hashed_pw, created_at) 
                VALUES ($1, $2, $3) 
                RETURNING user_id
                """,
                email, hashed_password, datetime.now()
            )
            
            await conn.close()
            
            logger.info(f"新規ユーザー作成成功: {email} (ID: {user_id})")
            return {
                "success": True, 
                "message": "ユーザー登録が完了しました",
                "user_id": user_id
            }
            
        except Exception as e:
            logger.error(f"ユーザー作成エラー: {e}")
            return {"success": False, "message": f"ユーザー作成に失敗しました: {str(e)}"}
    
    async def authenticate_user(self, email: str, password: str) -> Dict[str, Any]:
        """ユーザー認証"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # ユーザー情報を取得
            user = await conn.fetchrow(
                """
                SELECT user_id, email, hashed_pw, created_at, last_login, 
                       failed_login_counts, lock_until
                FROM users 
                WHERE email = $1
                """,
                email
            )
            
            if not user:
                await conn.close()
                return {"success": False, "message": "メールアドレスまたはパスワードが間違っています"}
            
            # アカウントロック確認
            if user['lock_until'] and user['lock_until'] > datetime.now():
                await conn.close()
                return {
                    "success": False, 
                    "message": f"アカウントがロックされています。{user['lock_until'].strftime('%H:%M')}以降に再試行してください"
                }
            
            # パスワード検証
            if not pwd_context.verify(password, user['hashed_pw']):
                # 失敗回数を増加
                await self._increment_failed_login(conn, user['user_id'], user['failed_login_counts'])
                await conn.close()
                return {"success": False, "message": "メールアドレスまたはパスワードが間違っています"}
            
            # ログイン成功 - last_loginを更新し、失敗回数をリセット
            await conn.execute(
                """
                UPDATE users 
                SET last_login = $1, failed_login_counts = 0, lock_until = NULL
                WHERE user_id = $2
                """,
                datetime.now(), user['user_id']
            )
            
            await conn.close()
            
            logger.info(f"ログイン成功: {email}")
            return {
                "success": True,
                "message": "ログインしました",
                "user": {
                    "user_id": user['user_id'],
                    "email": user['email'],
                    "created_at": user['created_at']
                }
            }
            
        except Exception as e:
            logger.error(f"認証エラー: {e}")
            return {"success": False, "message": "認証処理でエラーが発生しました"}
    
    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """ユーザーIDでユーザー情報を取得"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            user = await conn.fetchrow(
                """
                SELECT user_id, email, created_at, last_login
                FROM users 
                WHERE user_id = $1
                """,
                user_id
            )
            
            await conn.close()
            
            if user:
                return {
                    "user_id": user['user_id'],
                    "email": user['email'],
                    "created_at": user['created_at'],
                    "last_login": user['last_login']
                }
            
            return None
            
        except Exception as e:
            logger.error(f"ユーザー取得エラー: {e}")
            return None
    
    async def _increment_failed_login(self, conn: asyncpg.Connection, user_id: int, current_count: int):
        """ログイン失敗回数を増加（5回でロック）"""
        new_count = current_count + 1
        lock_until = None
        
        if new_count >= 5:
            # 15分間ロック
            lock_until = datetime.now() + timedelta(minutes=15)
            logger.warning(f"ユーザー {user_id} をアカウントロック: {lock_until}")
        
        await conn.execute(
            """
            UPDATE users 
            SET failed_login_counts = $1, lock_until = $2
            WHERE user_id = $3
            """,
            new_count, lock_until, user_id
        )

class SessionCRUD:
    """セッション関連のデータベース操作クラス"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
    
    async def create_session(self, user_id: int) -> Optional[str]:
        """新しいセッションを作成"""
        try:
            # セッションIDを生成
            session_id = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(minutes=30)  # 30分で期限切れ
            
            conn = await self.db_connection.get_async_connection()
            
            # 古いセッションを無効化
            await conn.execute(
                "UPDATE sessions SET is_active = FALSE WHERE user_id = $1",
                user_id
            )
            
            # 新しいセッションを作成
            await conn.execute(
                """
                INSERT INTO sessions (session_id, user_id, expires_at, is_active) 
                VALUES ($1, $2, $3, TRUE)
                """,
                session_id, user_id, expires_at
            )
            
            await conn.close()
            
            logger.info(f"セッション作成成功: {session_id} (ユーザー: {user_id})")
            return session_id
            
        except Exception as e:
            logger.error(f"セッション作成エラー: {e}")
            return None
    
    async def validate_session(self, session_id: str) -> Optional[int]:
        """セッションを検証してユーザーIDを返す"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            user_id = await conn.fetchval(
                """
                SELECT user_id 
                FROM sessions 
                WHERE session_id = $1 AND is_active = TRUE AND expires_at > $2
                """,
                session_id, datetime.now()
            )
            
            await conn.close()
            
            if user_id:
                logger.debug(f"セッション検証成功: {session_id}")
                return user_id
            
            return None
            
        except Exception as e:
            logger.error(f"セッション検証エラー: {e}")
            return None
    
    async def invalidate_session(self, session_id: str) -> bool:
        """セッションを無効化"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            result = await conn.execute(
                "UPDATE sessions SET is_active = FALSE WHERE session_id = $1",
                session_id
            )
            
            await conn.close()
            
            logger.info(f"セッション無効化: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"セッション無効化エラー: {e}")
            return False
    
    async def cleanup_expired_sessions(self) -> int:
        """期限切れセッションをクリーンアップ"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            result = await conn.execute(
                "DELETE FROM sessions WHERE expires_at < $1 OR is_active = FALSE",
                datetime.now() - timedelta(hours=24)  # 24時間前の無効セッションも削除
            )
            
            await conn.close()
            
            deleted_count = int(result.split()[-1])  # "DELETE 5" -> 5
            logger.info(f"期限切れセッションクリーンアップ: {deleted_count}件削除")
            return deleted_count
            
        except Exception as e:
            logger.error(f"セッションクリーンアップエラー: {e}")
            return 0