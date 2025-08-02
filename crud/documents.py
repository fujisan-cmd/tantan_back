# ドキュメント・ベクトルストレージ関連のCRUD操作
from typing import Optional, List, Dict, Any, Tuple
import asyncpg
from datetime import datetime
import logging
import os
import json

logger = logging.getLogger(__name__)

class DocumentCRUD:
    """ドキュメント関連のデータベース操作クラス"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
    
    async def create_document(self, user_id: int, project_id: int, file_name: str, 
                            file_path: str, file_type: str, file_size: int, 
                            source_type: str) -> Dict[str, Any]:
        """新しいドキュメントを登録"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # プロジェクトへのアクセス権限確認
            access = await conn.fetchval(
                "SELECT 1 FROM project_members WHERE project_id = $1 AND user_id = $2",
                project_id, user_id
            )
            
            if not access:
                await conn.close()
                return {"success": False, "message": "このプロジェクトへのアクセス権限がありません"}
            
            # ドキュメントを登録
            document_id = await conn.fetchval(
                """
                INSERT INTO documents (user_id, project_id, file_name, file_path, 
                                     file_type, file_size, source_type, uploaded_at) 
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8) 
                RETURNING document_id
                """,
                user_id, project_id, file_name, file_path, file_type, 
                file_size, source_type, datetime.now()
            )
            
            await conn.close()
            
            logger.info(f"ドキュメント登録成功: {file_name} (ID: {document_id})")
            return {
                "success": True,
                "document_id": document_id,
                "message": "ドキュメントが登録されました"
            }
            
        except Exception as e:
            logger.error(f"ドキュメント登録エラー: {e}")
            return {"success": False, "message": f"ドキュメント登録に失敗しました: {str(e)}"}
    
    async def get_project_documents(self, project_id: int, user_id: int) -> List[Dict[str, Any]]:
        """プロジェクトのドキュメント一覧を取得"""
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
            
            documents = await conn.fetch(
                """
                SELECT d.document_id, d.file_name, d.file_type, d.file_size,
                       d.source_type, d.uploaded_at, u.email as user_email
                FROM documents d
                JOIN users u ON d.user_id = u.user_id
                WHERE d.project_id = $1
                ORDER BY d.uploaded_at DESC
                """,
                project_id
            )
            
            await conn.close()
            
            return [dict(doc) for doc in documents]
            
        except Exception as e:
            logger.error(f"ドキュメント一覧取得エラー: {e}")
            return []
    
    async def delete_document(self, document_id: int, user_id: int) -> Dict[str, Any]:
        """ドキュメントを削除"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # ドキュメント情報とアクセス権限を確認
            doc_info = await conn.fetchrow(
                """
                SELECT d.file_path, d.project_id, pm.user_id
                FROM documents d
                JOIN project_members pm ON d.project_id = pm.project_id
                WHERE d.document_id = $1 AND (d.user_id = $2 OR pm.user_id = $2)
                """,
                document_id, user_id
            )
            
            if not doc_info:
                await conn.close()
                return {"success": False, "message": "ドキュメントが見つからないか、削除権限がありません"}
            
            # トランザクション開始
            async with conn.transaction():
                # 関連するチャンクも削除（CASCADE制約により自動削除されるが明示的に実行）
                await conn.execute(
                    "DELETE FROM document_chunks WHERE document_id = $1",
                    document_id
                )
                
                # ドキュメントを削除
                await conn.execute(
                    "DELETE FROM documents WHERE document_id = $1",
                    document_id
                )
            
            await conn.close()
            
            # ファイルシステムからも削除
            try:
                if os.path.exists(doc_info['file_path']):
                    os.remove(doc_info['file_path'])
                    logger.info(f"ファイル削除成功: {doc_info['file_path']}")
            except Exception as file_error:
                logger.warning(f"ファイル削除エラー: {file_error}")
            
            logger.info(f"ドキュメント削除成功: {document_id}")
            return {"success": True, "message": "ドキュメントが削除されました"}
            
        except Exception as e:
            logger.error(f"ドキュメント削除エラー: {e}")
            return {"success": False, "message": f"ドキュメント削除に失敗しました: {str(e)}"}
    
    async def get_document_by_id(self, document_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """ドキュメント詳細を取得"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            document = await conn.fetchrow(
                """
                SELECT d.document_id, d.file_name, d.file_path, d.file_type, 
                       d.file_size, d.source_type, d.uploaded_at, d.project_id
                FROM documents d
                JOIN project_members pm ON d.project_id = pm.project_id
                WHERE d.document_id = $1 AND pm.user_id = $2
                """,
                document_id, user_id
            )
            
            await conn.close()
            
            return dict(document) if document else None
            
        except Exception as e:
            logger.error(f"ドキュメント取得エラー: {e}")
            return None

class VectorStoreCRUD:
    """ベクトルストレージ関連のデータベース操作クラス"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
    
    async def store_document_chunks(self, document_id: int, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """ドキュメントのチャンクとベクトルを保存"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # トランザクション開始
            async with conn.transaction():
                # 既存のチャンクを削除
                await conn.execute(
                    "DELETE FROM document_chunks WHERE document_id = $1",
                    document_id
                )
                
                # 新しいチャンクを挿入
                for chunk in chunks:
                    await conn.execute(
                        """
                        INSERT INTO document_chunks (document_id, chunk_text, chunk_order, embedding, metadata)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        document_id,
                        chunk['text'],
                        chunk['order'],
                        chunk['embedding'],  # pgvectorの vector型
                        json.dumps(chunk.get('metadata', {}))
                    )
            
            await conn.close()
            
            logger.info(f"チャンク保存成功: ドキュメント {document_id}, {len(chunks)}チャンク")
            return {
                "success": True,
                "chunks_stored": len(chunks),
                "message": "チャンクとベクトルが保存されました"
            }
            
        except Exception as e:
            logger.error(f"チャンク保存エラー: {e}")
            return {"success": False, "message": f"チャンク保存に失敗しました: {str(e)}"}
    
    async def vector_search(self, query_embedding: List[float], limit: int = 10, 
                          project_id: Optional[int] = None, 
                          source_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """ベクトル類似検索を実行"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # ベースクエリ
            base_query = """
                SELECT dc.chunk_id, dc.document_id, dc.chunk_text, dc.metadata,
                       d.file_name, d.source_type, d.project_id,
                       (dc.embedding <-> $1::vector) as distance
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.document_id
            """
            
            params = [query_embedding]
            where_conditions = []
            param_counter = 2
            
            # プロジェクト絞り込み
            if project_id is not None:
                where_conditions.append(f"d.project_id = ${param_counter}")
                params.append(project_id)
                param_counter += 1
            
            # ソースタイプ絞り込み
            if source_types:
                placeholders = ",".join([f"${i}" for i in range(param_counter, param_counter + len(source_types))])
                where_conditions.append(f"d.source_type IN ({placeholders})")
                params.extend(source_types)
                param_counter += len(source_types)
            
            # WHERE句を追加
            if where_conditions:
                base_query += " WHERE " + " AND ".join(where_conditions)
            
            # 類似度順でソート・制限
            base_query += f" ORDER BY distance ASC LIMIT ${param_counter}"
            params.append(limit)
            
            results = await conn.fetch(base_query, *params)
            
            await conn.close()
            
            # 結果を整形
            search_results = []
            for result in results:
                search_results.append({
                    "chunk_id": result['chunk_id'],
                    "document_id": result['document_id'],
                    "document_name": result['file_name'],
                    "chunk_text": result['chunk_text'],
                    "similarity_score": 1.0 - result['distance'],  # 距離を類似度スコアに変換
                    "source_type": result['source_type'],
                    "project_id": result['project_id'],
                    "metadata": json.loads(result['metadata']) if result['metadata'] else {}
                })
            
            logger.info(f"ベクトル検索実行: {len(search_results)}件の結果")
            return search_results
            
        except Exception as e:
            logger.error(f"ベクトル検索エラー: {e}")
            return []
    
    async def get_document_chunks(self, document_id: int) -> List[Dict[str, Any]]:
        """ドキュメントのチャンク一覧を取得"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            chunks = await conn.fetch(
                """
                SELECT chunk_id, chunk_text, chunk_order, metadata
                FROM document_chunks
                WHERE document_id = $1
                ORDER BY chunk_order
                """,
                document_id
            )
            
            await conn.close()
            
            return [
                {
                    "chunk_id": chunk['chunk_id'],
                    "chunk_text": chunk['chunk_text'],
                    "chunk_order": chunk['chunk_order'],
                    "metadata": json.loads(chunk['metadata']) if chunk['metadata'] else {}
                }
                for chunk in chunks
            ]
            
        except Exception as e:
            logger.error(f"チャンク取得エラー: {e}")
            return []
    
    async def delete_document_chunks(self, document_id: int) -> bool:
        """ドキュメントのチャンクを削除"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            result = await conn.execute(
                "DELETE FROM document_chunks WHERE document_id = $1",
                document_id
            )
            
            await conn.close()
            
            logger.info(f"チャンク削除成功: ドキュメント {document_id}")
            return True
            
        except Exception as e:
            logger.error(f"チャンク削除エラー: {e}")
            return False
    
    async def get_vector_stats(self, project_id: Optional[int] = None) -> Dict[str, Any]:
        """ベクトルストレージの統計情報を取得"""
        try:
            conn = await self.db_connection.get_async_connection()
            
            # ベースクエリ
            if project_id:
                total_chunks = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM document_chunks dc
                    JOIN documents d ON dc.document_id = d.document_id
                    WHERE d.project_id = $1
                    """,
                    project_id
                )
                
                total_documents = await conn.fetchval(
                    "SELECT COUNT(*) FROM documents WHERE project_id = $1",
                    project_id
                )
            else:
                total_chunks = await conn.fetchval("SELECT COUNT(*) FROM document_chunks")
                total_documents = await conn.fetchval("SELECT COUNT(*) FROM documents")
            
            await conn.close()
            
            return {
                "total_documents": total_documents,
                "total_chunks": total_chunks,
                "avg_chunks_per_document": total_chunks / max(total_documents, 1)
            }
            
        except Exception as e:
            logger.error(f"統計情報取得エラー: {e}")
            return {"total_documents": 0, "total_chunks": 0, "avg_chunks_per_document": 0}