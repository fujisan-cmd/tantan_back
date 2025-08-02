# リサーチ・インタビュー関連のCRUD操作
from typing import Optional, List, Dict, Any
import asyncpg
from datetime import datetime, date
import logging
import json

logger = logging.getLogger(__name__)

class ResearchCRUD:
    """リサーチ関連のデータベース操作クラス"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
    
    async def create_research_result(self, edit_id: int, user_id: int, result_text: str, 
                                   source_summary: str, research_type: str = "general") -> Dict[str, Any]:
        """リサーチ結果を保存"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # 編集履歴の存在確認
            edit_exists = await conn.fetchval(
                "SELECT 1 FROM edit_history WHERE edit_id = $1",
                edit_id
            )
            
            if not edit_exists:
                await conn.close()
                return {"success": False, "message": "指定された編集履歴が見つかりません"}
            
            # リサーチ結果を保存
            research_id = await conn.fetchval(
                """
                INSERT INTO research_results (edit_id, user_id, result_text, source_summary, research_type, researched_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING research_id
                """,
                edit_id, user_id, result_text, source_summary, research_type, datetime.now()
            )
            
            await conn.close()
            
            logger.info(f"リサーチ結果保存成功: {research_id}")
            return {
                "success": True,
                "research_id": research_id,
                "message": "リサーチ結果が保存されました"
            }
            
        except Exception as e:
            logger.error(f"リサーチ結果保存エラー: {e}")
            return {"success": False, "message": f"リサーチ結果保存に失敗しました: {str(e)}"}
    
    async def get_project_research_results(self, project_id: int, user_id: int) -> List[Dict[str, Any]]:
        """プロジェクトのリサーチ結果一覧を取得"""
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
            
            results = await conn.fetch(
                """
                SELECT rr.research_id, rr.result_text, rr.source_summary, rr.research_type,
                       rr.researched_at, eh.version, u.email as user_email
                FROM research_results rr
                JOIN edit_history eh ON rr.edit_id = eh.edit_id
                JOIN users u ON rr.user_id = u.user_id
                WHERE eh.project_id = $1
                ORDER BY rr.researched_at DESC
                """,
                project_id
            )
            
            await conn.close()
            
            return [dict(result) for result in results]
            
        except Exception as e:
            logger.error(f"リサーチ結果一覧取得エラー: {e}")
            return []
    
    async def delete_research_result(self, research_id: int, user_id: int) -> Dict[str, Any]:
        """リサーチ結果を削除"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # 削除権限確認（作成者または同じプロジェクトのメンバー）
            access = await conn.fetchval(
                """
                SELECT 1 FROM research_results rr
                JOIN edit_history eh ON rr.edit_id = eh.edit_id
                JOIN project_members pm ON eh.project_id = pm.project_id
                WHERE rr.research_id = $1 AND (rr.user_id = $2 OR pm.user_id = $2)
                """,
                research_id, user_id
            )
            
            if not access:
                await conn.close()
                return {"success": False, "message": "削除権限がありません"}
            
            # リサーチ結果を削除
            result = await conn.execute(
                "DELETE FROM research_results WHERE research_id = $1",
                research_id
            )
            
            await conn.close()
            
            logger.info(f"リサーチ結果削除成功: {research_id}")
            return {"success": True, "message": "リサーチ結果が削除されました"}
            
        except Exception as e:
            logger.error(f"リサーチ結果削除エラー: {e}")
            return {"success": False, "message": f"リサーチ結果削除に失敗しました: {str(e)}"}
    
    async def get_research_result_by_id(self, research_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """リサーチ結果詳細を取得"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            result = await conn.fetchrow(
                """
                SELECT rr.research_id, rr.result_text, rr.source_summary, rr.research_type,
                       rr.researched_at, eh.version, eh.project_id, u.email as user_email
                FROM research_results rr
                JOIN edit_history eh ON rr.edit_id = eh.edit_id
                JOIN users u ON rr.user_id = u.user_id
                JOIN project_members pm ON eh.project_id = pm.project_id
                WHERE rr.research_id = $1 AND pm.user_id = $2
                """,
                research_id, user_id
            )
            
            await conn.close()
            
            return dict(result) if result else None
            
        except Exception as e:
            logger.error(f"リサーチ結果取得エラー: {e}")
            return None

class InterviewCRUD:
    """インタビュー関連のデータベース操作クラス"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
    
    async def create_interview_note(self, project_id: int, user_id: int, interviewee_name: str,
                                  interview_date: date, interview_type: str, interview_note: str,
                                  edit_id: Optional[int] = None) -> Dict[str, Any]:
        """インタビューメモを作成"""
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
            
            # インタビューメモを作成
            note_id = await conn.fetchval(
                """
                INSERT INTO interview_notes (project_id, user_id, interviewee_name, interview_date,
                                           interview_type, interview_note, edit_id, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING note_id
                """,
                project_id, user_id, interviewee_name, interview_date,
                interview_type, interview_note, edit_id, datetime.now()
            )
            
            await conn.close()
            
            logger.info(f"インタビューメモ作成成功: {note_id}")
            return {
                "success": True,
                "note_id": note_id,
                "message": "インタビューメモが作成されました"
            }
            
        except Exception as e:
            logger.error(f"インタビューメモ作成エラー: {e}")
            return {"success": False, "message": f"インタビューメモ作成に失敗しました: {str(e)}"}
    
    async def get_project_interview_notes(self, project_id: int, user_id: int) -> List[Dict[str, Any]]:
        """プロジェクトのインタビューメモ一覧を取得"""
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
            
            notes = await conn.fetch(
                """
                SELECT in_.note_id, in_.interviewee_name, in_.interview_date, in_.interview_type,
                       in_.interview_note, in_.created_at, u.email as user_email,
                       eh.version
                FROM interview_notes in_
                JOIN users u ON in_.user_id = u.user_id
                LEFT JOIN edit_history eh ON in_.edit_id = eh.edit_id
                WHERE in_.project_id = $1
                ORDER BY in_.interview_date DESC, in_.created_at DESC
                """,
                project_id
            )
            
            await conn.close()
            
            return [dict(note) for note in notes]
            
        except Exception as e:
            logger.error(f"インタビューメモ一覧取得エラー: {e}")
            return []
    
    async def update_interview_note(self, note_id: int, user_id: int, 
                                  interviewee_name: Optional[str] = None,
                                  interview_date: Optional[date] = None,
                                  interview_type: Optional[str] = None,
                                  interview_note: Optional[str] = None) -> Dict[str, Any]:
        """インタビューメモを更新"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # 更新権限確認（作成者または同じプロジェクトのメンバー）
            access = await conn.fetchval(
                """
                SELECT 1 FROM interview_notes in_
                JOIN project_members pm ON in_.project_id = pm.project_id
                WHERE in_.note_id = $1 AND (in_.user_id = $2 OR pm.user_id = $2)
                """,
                note_id, user_id
            )
            
            if not access:
                await conn.close()
                return {"success": False, "message": "更新権限がありません"}
            
            # 更新するフィールドを動的に構築
            update_fields = []
            params = []
            param_counter = 1
            
            if interviewee_name is not None:
                update_fields.append(f"interviewee_name = ${param_counter}")
                params.append(interviewee_name)
                param_counter += 1
            
            if interview_date is not None:
                update_fields.append(f"interview_date = ${param_counter}")
                params.append(interview_date)
                param_counter += 1
            
            if interview_type is not None:
                update_fields.append(f"interview_type = ${param_counter}")
                params.append(interview_type)
                param_counter += 1
            
            if interview_note is not None:
                update_fields.append(f"interview_note = ${param_counter}")
                params.append(interview_note)
                param_counter += 1
            
            if not update_fields:
                await conn.close()
                return {"success": False, "message": "更新する項目がありません"}
            
            # 更新クエリを実行
            query = f"UPDATE interview_notes SET {', '.join(update_fields)} WHERE note_id = ${param_counter}"
            params.append(note_id)
            
            await conn.execute(query, *params)
            
            await conn.close()
            
            logger.info(f"インタビューメモ更新成功: {note_id}")
            return {"success": True, "message": "インタビューメモが更新されました"}
            
        except Exception as e:
            logger.error(f"インタビューメモ更新エラー: {e}")
            return {"success": False, "message": f"インタビューメモ更新に失敗しました: {str(e)}"}
    
    async def delete_interview_note(self, note_id: int, user_id: int) -> Dict[str, Any]:
        """インタビューメモを削除"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # 削除権限確認（作成者または同じプロジェクトのメンバー）
            access = await conn.fetchval(
                """
                SELECT 1 FROM interview_notes in_
                JOIN project_members pm ON in_.project_id = pm.project_id
                WHERE in_.note_id = $1 AND (in_.user_id = $2 OR pm.user_id = $2)
                """,
                note_id, user_id
            )
            
            if not access:
                await conn.close()
                return {"success": False, "message": "削除権限がありません"}
            
            # インタビューメモを削除
            result = await conn.execute(
                "DELETE FROM interview_notes WHERE note_id = $1",
                note_id
            )
            
            await conn.close()
            
            logger.info(f"インタビューメモ削除成功: {note_id}")
            return {"success": True, "message": "インタビューメモが削除されました"}
            
        except Exception as e:
            logger.error(f"インタビューメモ削除エラー: {e}")
            return {"success": False, "message": f"インタビューメモ削除に失敗しました: {str(e)}"}
    
    async def get_interview_note_by_id(self, note_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """インタビューメモ詳細を取得"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            note = await conn.fetchrow(
                """
                SELECT in_.note_id, in_.interviewee_name, in_.interview_date, in_.interview_type,
                       in_.interview_note, in_.created_at, in_.project_id, u.email as user_email,
                       eh.version
                FROM interview_notes in_
                JOIN users u ON in_.user_id = u.user_id
                LEFT JOIN edit_history eh ON in_.edit_id = eh.edit_id
                JOIN project_members pm ON in_.project_id = pm.project_id
                WHERE in_.note_id = $1 AND pm.user_id = $2
                """,
                note_id, user_id
            )
            
            await conn.close()
            
            return dict(note) if note else None
            
        except Exception as e:
            logger.error(f"インタビューメモ取得エラー: {e}")
            return None
    
    async def link_interview_to_edit(self, note_id: int, edit_id: int, user_id: int) -> Dict[str, Any]:
        """インタビューメモを特定の編集履歴に関連付け"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # 権限確認（同じプロジェクトのメンバー）
            access = await conn.fetchval(
                """
                SELECT 1 FROM interview_notes in_
                JOIN edit_history eh ON $2 = eh.edit_id
                JOIN project_members pm ON in_.project_id = pm.project_id AND eh.project_id = pm.project_id
                WHERE in_.note_id = $1 AND pm.user_id = $3
                """,
                note_id, edit_id, user_id
            )
            
            if not access:
                await conn.close()
                return {"success": False, "message": "関連付け権限がありません"}
            
            # インタビューメモを編集履歴に関連付け
            await conn.execute(
                "UPDATE interview_notes SET edit_id = $1 WHERE note_id = $2",
                edit_id, note_id
            )
            
            await conn.close()
            
            logger.info(f"インタビューメモ関連付け成功: メモ {note_id} → 編集 {edit_id}")
            return {"success": True, "message": "インタビューメモが編集履歴に関連付けられました"}
            
        except Exception as e:
            logger.error(f"インタビューメモ関連付けエラー: {e}")
            return {"success": False, "message": f"関連付けに失敗しました: {str(e)}"}
    
    async def get_interview_notes_by_edit(self, edit_id: int, user_id: int) -> List[Dict[str, Any]]:
        """特定の編集履歴に関連するインタビューメモを取得"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            notes = await conn.fetch(
                """
                SELECT in_.note_id, in_.interviewee_name, in_.interview_date, in_.interview_type,
                       in_.interview_note, in_.created_at, u.email as user_email
                FROM interview_notes in_
                JOIN users u ON in_.user_id = u.user_id
                JOIN edit_history eh ON in_.edit_id = eh.edit_id
                JOIN project_members pm ON eh.project_id = pm.project_id
                WHERE in_.edit_id = $1 AND pm.user_id = $2
                ORDER BY in_.interview_date DESC, in_.created_at DESC
                """,
                edit_id, user_id
            )
            
            await conn.close()
            
            return [dict(note) for note in notes]
            
        except Exception as e:
            logger.error(f"編集関連インタビューメモ取得エラー: {e}")
            return []