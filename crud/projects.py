# プロジェクト関連のCRUD操作
from typing import Optional, List, Dict, Any, Tuple
import asyncpg
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

class ProjectCRUD:
    """プロジェクト関連のデータベース操作クラス"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
    
    async def create_project(self, user_id: int, project_name: str, canvas_data: Dict[str, Any], 
                           update_comment: Optional[str] = None) -> Dict[str, Any]:
        """新しいプロジェクトを作成"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # トランザクション開始
            async with conn.transaction():
                # プロジェクトを作成
                project_id = await conn.fetchval(
                    """
                    INSERT INTO projects (user_id, project_name, created_at) 
                    VALUES ($1, $2, $3) 
                    RETURNING project_id
                    """,
                    user_id, project_name, datetime.now()
                )
                
                # 編集履歴を作成（バージョン1）
                edit_id = await conn.fetchval(
                    """
                    INSERT INTO edit_history (project_id, version, user_id, update_category, update_comment) 
                    VALUES ($1, 1, $2, 'manual', $3) 
                    RETURNING edit_id
                    """,
                    project_id, user_id, update_comment or "初期作成"
                )
                
                # キャンバス詳細を保存
                await conn.execute(
                    """
                    INSERT INTO details (
                        edit_id, problem, customer_segments, unique_value_proposition,
                        solution, channels, revenue_streams, cost_structure,
                        key_metrics, unfair_advantage, early_adopters, existing_alternatives
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    """,
                    edit_id,
                    canvas_data.get('problem'),
                    canvas_data.get('customer_segments'),
                    canvas_data.get('unique_value_proposition'),
                    canvas_data.get('solution'),
                    canvas_data.get('channels'),
                    canvas_data.get('revenue_streams'),
                    canvas_data.get('cost_structure'),
                    canvas_data.get('key_metrics'),
                    canvas_data.get('unfair_advantage'),
                    canvas_data.get('early_adopters'),
                    canvas_data.get('existing_alternatives')
                )
                
                # プロジェクトメンバーに追加（作成者はadmin）
                await conn.execute(
                    """
                    INSERT INTO project_members (project_id, user_id, role) 
                    VALUES ($1, $2, 'admin')
                    """,
                    project_id, user_id
                )
            
            await conn.close()
            
            logger.info(f"プロジェクト作成成功: {project_name} (ID: {project_id})")
            return {
                "success": True,
                "project_id": project_id,
                "edit_id": edit_id,
                "version": 1,
                "message": "プロジェクトが作成されました"
            }
            
        except Exception as e:
            logger.error(f"プロジェクト作成エラー: {e}")
            return {"success": False, "message": f"プロジェクト作成に失敗しました: {str(e)}"}
    
    async def get_user_projects(self, user_id: int) -> List[Dict[str, Any]]:
        """ユーザーのプロジェクト一覧を取得"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            projects = await conn.fetch(
                """
                SELECT p.project_id, p.project_name, p.created_at,
                       eh.last_updated, eh.version as current_version
                FROM projects p
                JOIN project_members pm ON p.project_id = pm.project_id
                JOIN edit_history eh ON p.project_id = eh.project_id
                WHERE pm.user_id = $1
                AND eh.version = (
                    SELECT MAX(version) FROM edit_history 
                    WHERE project_id = p.project_id
                )
                ORDER BY eh.last_updated DESC
                """,
                user_id
            )
            
            await conn.close()
            
            return [dict(project) for project in projects]
            
        except Exception as e:
            logger.error(f"プロジェクト一覧取得エラー: {e}")
            return []
    
    async def get_project_latest(self, project_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """プロジェクトの最新バージョンを取得"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # アクセス権限確認
            access = await conn.fetchval(
                "SELECT 1 FROM project_members WHERE project_id = $1 AND user_id = $2",
                project_id, user_id
            )
            
            if not access:
                await conn.close()
                return None
            
            # 最新バージョンの編集履歴を取得
            edit_history = await conn.fetchrow(
                """
                SELECT eh.edit_id, eh.version, eh.last_updated, eh.update_category, 
                       eh.update_comment, p.project_name, p.created_at
                FROM edit_history eh
                JOIN projects p ON eh.project_id = p.project_id
                WHERE eh.project_id = $1
                ORDER BY eh.version DESC
                LIMIT 1
                """,
                project_id
            )
            
            if not edit_history:
                await conn.close()
                return None
            
            # キャンバス詳細を取得
            details = await conn.fetchrow(
                """
                SELECT problem, customer_segments, unique_value_proposition,
                       solution, channels, revenue_streams, cost_structure,
                       key_metrics, unfair_advantage, early_adopters, existing_alternatives
                FROM details 
                WHERE edit_id = $1
                """,
                edit_history['edit_id']
            )
            
            await conn.close()
            
            canvas_data = dict(details) if details else {}
            
            return {
                "project_id": project_id,
                "project_name": edit_history['project_name'],
                "created_at": edit_history['created_at'],
                "current_version": edit_history['version'],
                "last_updated": edit_history['last_updated'],
                "update_category": edit_history['update_category'],
                "update_comment": edit_history['update_comment'],
                "canvas_data": canvas_data
            }
            
        except Exception as e:
            logger.error(f"プロジェクト取得エラー: {e}")
            return None
    
    async def update_project(self, project_id: int, user_id: int, canvas_data: Dict[str, Any], 
                           update_category: str = "manual", update_comment: Optional[str] = None) -> Dict[str, Any]:
        """プロジェクトを更新（新しいバージョンを作成）"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # アクセス権限確認
            access = await conn.fetchval(
                "SELECT 1 FROM project_members WHERE project_id = $1 AND user_id = $2",
                project_id, user_id
            )
            
            if not access:
                await conn.close()
                return {"success": False, "message": "このプロジェクトへのアクセス権限がありません"}
            
            # トランザクション開始
            async with conn.transaction():
                # 現在の最大バージョンを取得
                max_version = await conn.fetchval(
                    "SELECT COALESCE(MAX(version), 0) FROM edit_history WHERE project_id = $1",
                    project_id
                )
                
                new_version = max_version + 1
                
                # 新しい編集履歴を作成
                edit_id = await conn.fetchval(
                    """
                    INSERT INTO edit_history (project_id, version, user_id, update_category, update_comment) 
                    VALUES ($1, $2, $3, $4, $5) 
                    RETURNING edit_id
                    """,
                    project_id, new_version, user_id, update_category, update_comment
                )
                
                # キャンバス詳細を保存
                await conn.execute(
                    """
                    INSERT INTO details (
                        edit_id, problem, customer_segments, unique_value_proposition,
                        solution, channels, revenue_streams, cost_structure,
                        key_metrics, unfair_advantage, early_adopters, existing_alternatives
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    """,
                    edit_id,
                    canvas_data.get('problem'),
                    canvas_data.get('customer_segments'),
                    canvas_data.get('unique_value_proposition'),
                    canvas_data.get('solution'),
                    canvas_data.get('channels'),
                    canvas_data.get('revenue_streams'),
                    canvas_data.get('cost_structure'),
                    canvas_data.get('key_metrics'),
                    canvas_data.get('unfair_advantage'),
                    canvas_data.get('early_adopters'),
                    canvas_data.get('existing_alternatives')
                )
            
            await conn.close()
            
            logger.info(f"プロジェクト更新成功: {project_id} (バージョン: {new_version})")
            return {
                "success": True,
                "edit_id": edit_id,
                "version": new_version,
                "message": "プロジェクトが更新されました"
            }
            
        except Exception as e:
            logger.error(f"プロジェクト更新エラー: {e}")
            return {"success": False, "message": f"プロジェクト更新に失敗しました: {str(e)}"}
    
    async def delete_project(self, project_id: int, user_id: int) -> Dict[str, Any]:
        """プロジェクトを削除"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # 管理者権限確認
            access = await conn.fetchval(
                """
                SELECT 1 FROM project_members 
                WHERE project_id = $1 AND user_id = $2 AND role = 'admin'
                """,
                project_id, user_id
            )
            
            if not access:
                await conn.close()
                return {"success": False, "message": "削除権限がありません"}
            
            # トランザクション開始（CASCADE制約により関連データも削除）
            async with conn.transaction():
                # プロジェクトを削除（CASCADE制約により関連データも削除される）
                result = await conn.execute(
                    "DELETE FROM projects WHERE project_id = $1",
                    project_id
                )
            
            await conn.close()
            
            logger.info(f"プロジェクト削除成功: {project_id}")
            return {"success": True, "message": "プロジェクトが削除されました"}
            
        except Exception as e:
            logger.error(f"プロジェクト削除エラー: {e}")
            return {"success": False, "message": f"プロジェクト削除に失敗しました: {str(e)}"}
    
    async def get_edit_history(self, project_id: int, user_id: int) -> List[Dict[str, Any]]:
        """プロジェクトの編集履歴を取得"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # アクセス権限確認
            access = await conn.fetchval(
                "SELECT 1 FROM project_members WHERE project_id = $1 AND user_id = $2",
                project_id, user_id
            )
            
            if not access:
                await conn.close()
                return []
            
            history = await conn.fetch(
                """
                SELECT eh.edit_id, eh.version, eh.last_updated, eh.update_category, 
                       eh.update_comment, u.email as user_email
                FROM edit_history eh
                JOIN users u ON eh.user_id = u.user_id
                WHERE eh.project_id = $1
                ORDER BY eh.version DESC
                """,
                project_id
            )
            
            await conn.close()
            
            return [dict(item) for item in history]
            
        except Exception as e:
            logger.error(f"編集履歴取得エラー: {e}")
            return []
    
    async def rollback_to_version(self, project_id: int, edit_id: int, user_id: int, 
                                rollback_comment: Optional[str] = None) -> Dict[str, Any]:
        """指定したバージョンにロールバック"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # アクセス権限確認
            access = await conn.fetchval(
                "SELECT 1 FROM project_members WHERE project_id = $1 AND user_id = $2",
                project_id, user_id
            )
            
            if not access:
                await conn.close()
                return {"success": False, "message": "このプロジェクトへのアクセス権限がありません"}
            
            # ロールバック対象のデータを取得
            target_details = await conn.fetchrow(
                """
                SELECT d.problem, d.customer_segments, d.unique_value_proposition,
                       d.solution, d.channels, d.revenue_streams, d.cost_structure,
                       d.key_metrics, d.unfair_advantage, d.early_adopters, d.existing_alternatives,
                       eh.version as target_version
                FROM details d
                JOIN edit_history eh ON d.edit_id = eh.edit_id
                WHERE d.edit_id = $1 AND eh.project_id = $2
                """,
                edit_id, project_id
            )
            
            if not target_details:
                await conn.close()
                return {"success": False, "message": "ロールバック対象のバージョンが見つかりません"}
            
            # トランザクション開始
            async with conn.transaction():
                # 現在の最大バージョンを取得
                max_version = await conn.fetchval(
                    "SELECT COALESCE(MAX(version), 0) FROM edit_history WHERE project_id = $1",
                    project_id
                )
                
                new_version = max_version + 1
                
                # 新しい編集履歴を作成（ロールバック）
                new_edit_id = await conn.fetchval(
                    """
                    INSERT INTO edit_history (project_id, version, user_id, update_category, update_comment) 
                    VALUES ($1, $2, $3, 'rollback', $4) 
                    RETURNING edit_id
                    """,
                    project_id, new_version, user_id, 
                    rollback_comment or f"バージョン{target_details['target_version']}にロールバック"
                )
                
                # ロールバック対象のデータを新バージョンとして保存
                await conn.execute(
                    """
                    INSERT INTO details (
                        edit_id, problem, customer_segments, unique_value_proposition,
                        solution, channels, revenue_streams, cost_structure,
                        key_metrics, unfair_advantage, early_adopters, existing_alternatives
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    """,
                    new_edit_id,
                    target_details['problem'],
                    target_details['customer_segments'],
                    target_details['unique_value_proposition'],
                    target_details['solution'],
                    target_details['channels'],
                    target_details['revenue_streams'],
                    target_details['cost_structure'],
                    target_details['key_metrics'],
                    target_details['unfair_advantage'],
                    target_details['early_adopters'],
                    target_details['existing_alternatives']
                )
            
            await conn.close()
            
            logger.info(f"ロールバック成功: プロジェクト {project_id}, バージョン {target_details['target_version']} → {new_version}")
            return {
                "success": True,
                "edit_id": new_edit_id,
                "version": new_version,
                "target_version": target_details['target_version'],
                "message": f"バージョン{target_details['target_version']}にロールバックしました"
            }
            
        except Exception as e:
            logger.error(f"ロールバックエラー: {e}")
            return {"success": False, "message": f"ロールバックに失敗しました: {str(e)}"}
    
    async def compare_canvas_versions(self, project_id: int, edit_id1: int, edit_id2: int) -> Dict[str, Any]:
        """2つのキャンバスバージョンを比較"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # 両方のバージョンを取得
            version1 = await conn.fetchrow(
                """
                SELECT problem, customer_segments, unique_value_proposition,
                       solution, channels, revenue_streams, cost_structure,
                       key_metrics, unfair_advantage, early_adopters, existing_alternatives
                FROM details WHERE edit_id = $1
                """,
                edit_id1
            )
            
            version2 = await conn.fetchrow(
                """
                SELECT problem, customer_segments, unique_value_proposition,
                       solution, channels, revenue_streams, cost_structure,
                       key_metrics, unfair_advantage, early_adopters, existing_alternatives
                FROM details WHERE edit_id = $2
                """,
                edit_id2
            )
            
            await conn.close()
            
            if not version1 or not version2:
                return {"success": False, "message": "比較対象のバージョンが見つかりません"}
            
            # 差分を計算
            differences = {}
            fields = [
                'problem', 'customer_segments', 'unique_value_proposition',
                'solution', 'channels', 'revenue_streams', 'cost_structure',
                'key_metrics', 'unfair_advantage', 'early_adopters', 'existing_alternatives'
            ]
            
            for field in fields:
                val1 = version1[field] or ""
                val2 = version2[field] or ""
                differences[field] = {
                    "version1": val1,
                    "version2": val2,
                    "changed": val1 != val2
                }
            
            return {
                "success": True,
                "version1": dict(version1),
                "version2": dict(version2),
                "differences": differences
            }
            
        except Exception as e:
            logger.error(f"バージョン比較エラー: {e}")
            return {"success": False, "message": f"バージョン比較に失敗しました: {str(e)}"}