import pymysql
from datetime import datetime, timedelta
from typing import Dict, Any
from database import db_connection

class RateLimiter:
    """IPベースのレート制限機能"""
    
    @staticmethod
    def check_rate_limit(ip_address: str, action: str = "login", limit: int = 5, window_minutes: int = 15) -> Dict[str, Any]:
        """
        レート制限をチェック
        
        Args:
            ip_address: クライアントのIPアドレス
            action: アクション種別（login, signup等）
            limit: 制限回数
            window_minutes: 制限時間（分）
        
        Returns:
            {"allowed": bool, "remaining": int, "reset_time": datetime}
        """
        cursor = None
        try:
            conn = db_connection.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            
            # 指定時間内の試行回数を取得
            since_time = datetime.now() - timedelta(minutes=window_minutes)
            
            cursor.execute("""
                SELECT COUNT(*) as attempt_count 
                FROM login_attempts 
                WHERE ip_address = %s 
                AND attempt_time > %s
            """, (ip_address, since_time))
            
            result = cursor.fetchone()
            attempt_count = result['attempt_count'] if result else 0
            
            remaining = max(0, limit - attempt_count)
            reset_time = datetime.now() + timedelta(minutes=window_minutes)
            
            return {
                "allowed": attempt_count < limit,
                "remaining": remaining,
                "reset_time": reset_time,
                "attempt_count": attempt_count
            }
            
        except pymysql.Error as e:
            print(f"レート制限チェックエラー: {e}")
            # エラー時は制限を適用せず許可
            return {
                "allowed": True,
                "remaining": limit,
                "reset_time": datetime.now() + timedelta(minutes=window_minutes),
                "attempt_count": 0
            }
        finally:
            if cursor:
                cursor.close()
    
    @staticmethod
    def record_attempt(ip_address: str, user_id: int = None, success: bool = False):
        """
        ログイン試行を記録
        
        Args:
            ip_address: クライアントのIPアドレス
            user_id: ユーザーID（存在する場合）
            success: 成功フラグ
        """
        cursor = None
        try:
            conn = db_connection.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO login_attempts (user_id, attempt_time, success, ip_address)
                VALUES (%s, %s, %s, %s)
            """, (user_id, datetime.now(), success, ip_address))
            
            # 古いレコードを削除（パフォーマンス対策）
            cleanup_time = datetime.now() - timedelta(days=7)
            cursor.execute("""
                DELETE FROM login_attempts 
                WHERE attempt_time < %s
            """, (cleanup_time,))
            
        except pymysql.Error as e:
            print(f"ログイン試行記録エラー: {e}")
        finally:
            if cursor:
                cursor.close()
    
    @staticmethod
    def get_client_ip(request) -> str:
        """
        リクエストからクライアントIPを取得
        プロキシ経由の場合も考慮
        """
        # X-Forwarded-For ヘッダーをチェック（プロキシ経由の場合）
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            # 最初のIPアドレスを取得（複数ある場合）
            return forwarded_for.split(',')[0].strip()
        
        # X-Real-IP ヘッダーをチェック
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip.strip()
        
        # 直接接続の場合
        return request.client.host