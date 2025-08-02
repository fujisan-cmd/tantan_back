import pymysql
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from database import db_connection
from auth import get_password_hash, verify_password, validate_password

class UserService:
    """ユーザー関連のビジネスロジック"""
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """メールアドレス形式を検証"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def create_user(email: str, password: str) -> Dict[str, Any]:
        """新規ユーザーを作成"""
        # バリデーション
        if not UserService.validate_email(email):
            return {"success": False, "message": "有効なメールアドレスを入力してください"}
        
        if not validate_password(password):
            return {"success": False, "message": "パスワードは半角英数字および記号(!#$%^&*)を含む8文字以上で入力してください。記号は必須です。"}
        
        cursor = None
        try:
            conn = db_connection.get_connection()
            cursor = conn.cursor()
            
            # メールアドレスの重複チェック
            cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                return {"success": False, "message": "このメールアドレスは既に使用されています"}
            
            # パスワードをハッシュ化
            hashed_password = get_password_hash(password)
            
            # ユーザーを挿入
            cursor.execute(
                "INSERT INTO users (email, hashed_pw, created_at) VALUES (%s, %s, %s)",
                (email, hashed_password, datetime.now())
            )
            
            # 作成されたユーザーIDを取得
            user_id = cursor.lastrowid
            
            return {
                "success": True, 
                "message": "ユーザー登録が完了しました",
                "user_id": user_id
            }
            
        except pymysql.Error as e:
            return {"success": False, "message": f"データベースエラー: {str(e)}"}
        finally:
            if cursor:
                cursor.close()
    
    @staticmethod
    def authenticate_user(email: str, password: str) -> Dict[str, Any]:
        """ユーザー認証"""
        cursor = None
        try:
            conn = db_connection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            
            # ユーザー情報を取得
            cursor.execute(
                "SELECT user_id, email, hashed_pw, created_at, failed_login_counts, lock_until FROM users WHERE email = %s",
                (email,)
            )
            user = cursor.fetchone()
            
            if not user:
                return {"success": False, "message": "メールアドレスまたはパスワードが違います"}
            
            # アカウントロックチェック
            if user['lock_until'] and user['lock_until'] > datetime.now():
                return {"success": False, "message": "アカウントがロックされています。しばらく時間をおいて再試行してください"}
            
            # パスワード検証
            if not verify_password(password, user['hashed_pw']):
                # 失敗回数を増加
                UserService._increment_failed_login(user['user_id'])
                return {"success": False, "message": "メールアドレスまたはパスワードが違います"}
            
            # ログイン成功時の処理
            UserService._reset_failed_login(user['user_id'])
            UserService._update_last_login(user['user_id'])
            
            return {
                "success": True,
                "message": "ログインに成功しました",
                "user": {
                    "user_id": user['user_id'],
                    "email": user['email'],
                    "created_at": user['created_at']
                }
            }
            
        except pymysql.Error as e:
            return {"success": False, "message": f"データベースエラー: {str(e)}"}
        finally:
            if cursor:
                cursor.close()
    
    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        """ユーザーIDからユーザー情報を取得"""
        cursor = None
        try:
            conn = db_connection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            
            cursor.execute(
                "SELECT user_id, email, created_at, last_login FROM users WHERE user_id = %s",
                (user_id,)
            )
            user = cursor.fetchone()
            
            if user:
                return {
                    "user_id": user['user_id'],
                    "email": user['email'],
                    "created_at": user['created_at'],
                    "last_login": user['last_login']
                }
            return None
            
        except pymysql.Error as e:
            print(f"データベースエラー: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
    
    @staticmethod
    def _increment_failed_login(user_id: int):
        """ログイン失敗回数を増加"""
        cursor = None
        try:
            conn = db_connection.get_connection()
            cursor = conn.cursor()
            
            # 失敗回数を取得
            cursor.execute("SELECT failed_login_counts FROM users WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            failed_count = (result[0] if result else 0) + 1
            
            # 3回失敗でロック
            lock_until = None
            if failed_count >= 3:
                lock_until = datetime.now() + timedelta(minutes=5)
            
            cursor.execute(
                "UPDATE users SET failed_login_counts = %s, lock_until = %s WHERE user_id = %s",
                (failed_count, lock_until, user_id)
            )
            
        except pymysql.Error as e:
            print(f"ログイン失敗回数更新エラー: {e}")
        finally:
            if cursor:
                cursor.close()
    
    @staticmethod
    def _reset_failed_login(user_id: int):
        """ログイン失敗回数をリセット"""
        cursor = None
        try:
            conn = db_connection.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE users SET failed_login_counts = 0, lock_until = NULL WHERE user_id = %s",
                (user_id,)
            )
            
        except pymysql.Error as e:
            print(f"ログイン失敗回数リセットエラー: {e}")
        finally:
            if cursor:
                cursor.close()
    
    @staticmethod
    def _update_last_login(user_id: int):
        """最終ログイン時刻を更新"""
        cursor = None
        try:
            conn = db_connection.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE users SET last_login = %s WHERE user_id = %s",
                (datetime.now(), user_id)
            )
            
        except pymysql.Error as e:
            print(f"最終ログイン時刻更新エラー: {e}")
        finally:
            if cursor:
                cursor.close()


class SessionService:
    """セッション管理サービス"""
    
    @staticmethod
    def create_session(user_id: int) -> str:
        """新しいセッションを作成"""
        cursor = None
        try:
            conn = db_connection.get_connection()
            cursor = conn.cursor()
            
            # 既存のアクティブセッションを無効化
            cursor.execute(
                "UPDATE sessions SET is_active = FALSE WHERE user_id = %s AND is_active = TRUE",
                (user_id,)
            )
            
            # 新しいセッションを作成
            session_id = str(uuid.uuid4())
            expires_at = datetime.now() + timedelta(minutes=15)  # 15分後に期限切れ
            
            cursor.execute(
                "INSERT INTO sessions (session_id, user_id, created_at, expires_at, is_active) VALUES (%s, %s, %s, %s, %s)",
                (session_id, user_id, datetime.now(), expires_at, True)
            )
            
            return session_id
            
        except pymysql.Error as e:
            print(f"セッション作成エラー: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
    
    @staticmethod
    def validate_session(session_id: str) -> Optional[int]:
        """セッションを検証し、ユーザーIDを返す"""
        cursor = None
        try:
            conn = db_connection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            
            cursor.execute(
                "SELECT user_id, expires_at FROM sessions WHERE session_id = %s AND is_active = TRUE",
                (session_id,)
            )
            session = cursor.fetchone()
            
            if not session:
                return None
            
            # 期限切れチェック
            if session['expires_at'] < datetime.now():
                # 期限切れセッションを無効化
                SessionService.invalidate_session(session_id)
                return None
            
            return session['user_id']
            
        except pymysql.Error as e:
            print(f"セッション検証エラー: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
    
    @staticmethod
    def invalidate_session(session_id: str):
        """セッションを無効化"""
        cursor = None
        try:
            conn = db_connection.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE sessions SET is_active = FALSE WHERE session_id = %s",
                (session_id,)
            )
            
        except pymysql.Error as e:
            print(f"セッション無効化エラー: {e}")
        finally:
            if cursor:
                cursor.close()