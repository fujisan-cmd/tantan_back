# RAG（Retrieval-Augmented Generation）サービス
import os
import openai
from typing import List, Dict, Any, Optional
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
import tiktoken
import logging
from datetime import datetime
import json
import psycopg2
from psycopg2.extras import Json

# 現在のプロジェクト構造に合わせてインポート修正
from connect_PostgreSQL import SessionLocal
from sqlalchemy import text

logger = logging.getLogger(__name__)

class RAGService:
    """RAG関連のビジネスロジック"""
    
    def __init__(self):
        # OpenAI設定
        self.api_key = os.getenv("API_KEY")
        if not self.api_key:
            logger.warning("API_KEYが設定されていません")
        
        openai.api_key = self.api_key
        
        self.model = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
        self.embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
        
        # テキスト分割設定
        self.chunk_size = int(os.getenv("CHUNK_SIZE", "1000"))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "150"))
        
        # LangChainコンポーネント初期化
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", "。", "．", " ", ""]
        )
        
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=self.api_key,
            model=self.embedding_model
        )
        
        # トークン計算用エンコーダー
        self.encoding = tiktoken.encoding_for_model("gpt-4")
    
    async def process_text_for_rag(self, document_id: int, text_content: str) -> Dict[str, Any]:
        """テキストをRAG用に処理（チャンク化＋ベクトル化）"""
        try:
            # テキストをチャンクに分割
            chunks = self.text_splitter.split_text(text_content)
            
            if not chunks:
                return {"success": False, "message": "テキストの分割に失敗しました"}
            
            # 各チャンクのベクトル埋め込みを生成
            chunk_data = []
            for i, chunk_text in enumerate(chunks):
                try:
                    # ベクトル埋め込み生成
                    embedding = await self._get_embedding(chunk_text)
                    
                    # メタデータ作成
                    metadata = {
                        "chunk_length": len(chunk_text),
                        "token_count": len(self.encoding.encode(chunk_text)),
                        "processed_at": datetime.now().isoformat()
                    }
                    
                    chunk_data.append({
                        "text": chunk_text,
                        "order": i,
                        "embedding": embedding,
                        "metadata": metadata
                    })
                    
                except Exception as e:
                    logger.error(f"チャンク {i} の処理エラー: {e}")
                    continue
            
            if not chunk_data:
                return {"success": False, "message": "ベクトル埋め込み生成に失敗しました"}
            
            # データベースに保存
            result = await self._store_document_chunks(document_id, chunk_data)
            
            # 保存結果をチェック
            if not result.get("success", False):
                logger.error(f"チャンク保存失敗: {result.get('message', 'Unknown error')}")
                return {
                    "success": False,
                    "message": f"チャンクの保存に失敗しました: {result.get('message', 'Unknown error')}"
                }
            
            logger.info(f"ドキュメント処理完了: {document_id}, {len(chunk_data)}チャンク, 保存確認済み")
            return {
                "success": True,
                "chunks_processed": len(chunk_data),
                "total_tokens": sum(chunk["metadata"]["token_count"] for chunk in chunk_data),
                "message": "ドキュメントのRAG処理が完了しました",
                "storage_result": result  # デバッグ用
            }
            
        except Exception as e:
            logger.error(f"ドキュメントRAG処理エラー: {e}")
            return {"success": False, "message": f"RAG処理に失敗しました: {str(e)}"}
    
    async def search_relevant_content(self, query: str, project_id: Optional[int] = None, 
                                    limit: int = 10) -> List[Dict[str, Any]]:
        """関連コンテンツを検索"""
        try:
            # クエリのベクトル埋め込みを生成
            query_embedding = await self._get_embedding(query)
            
            # ベクトル検索実行
            search_results = await self._vector_search(
                query_embedding=query_embedding,
                limit=limit,
                project_id=project_id
            )
            
            logger.info(f"ベクトル検索完了: クエリ='{query}', 結果数={len(search_results)}")
            return search_results
            
        except Exception as e:
            logger.error(f"ベクトル検索エラー: {e}")
            return []
    
    async def generate_canvas_from_idea(self, idea_description: str, target_audience: Optional[str] = None,
                                      industry: Optional[str] = None) -> Dict[str, Any]:
        """アイデアからリーンキャンバスを自動生成"""
        try:
            # プロンプト構築
            system_prompt = self._build_canvas_generation_prompt()
            user_prompt = self._build_user_canvas_prompt(idea_description, target_audience, industry)
            
            # OpenAI APIを呼び出し（新しいAPI形式）
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.api_key)
            
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            # レスポンスを解析
            generated_content = response.choices[0].message.content
            canvas_data = self._parse_canvas_response(generated_content)
            
            logger.info(f"キャンバス自動生成完了: アイデア='{idea_description[:50]}...'")
            return {
                "success": True,
                "canvas_data": canvas_data,
                "raw_response": generated_content,
                "message": "リーンキャンバスが自動生成されました"
            }
            
        except Exception as e:
            logger.error(f"キャンバス自動生成エラー: {e}")
            return {"success": False, "message": f"キャンバス生成に失敗しました: {str(e)}"}
    
    async def _get_embedding(self, text: str) -> List[float]:
        """テキストのベクトル埋め込みを取得"""
        try:
            # LangChainの埋め込みを使用
            embedding = await self.embeddings.aembed_query(text)
            return embedding
        except Exception as e:
            logger.error(f"埋め込み生成エラー: {e}")
            raise
    
    async def _store_document_chunks(self, document_id: int, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """ドキュメントのチャンクとベクトルを保存（直接psycopg2を使用）"""
        logger.info(f"[DEBUG] チャンク保存開始: document_id={document_id}, chunks数={len(chunks)}")
        
        # SQLAlchemy接続から生のpsycopg2接続を取得
        db = SessionLocal()
        try:
            # SQLAlchemyのコネクションから生のpsycopg2コネクションを取得
            connection = db.get_bind().raw_connection()
            cursor = connection.cursor()
            
            try:
                # 既存のチャンクを削除
                logger.info(f"[DEBUG] 既存チャンク削除: document_id={document_id}")
                cursor.execute(
                    "DELETE FROM document_chunks WHERE document_id = %s",
                    (document_id,)
                )
                logger.info(f"[DEBUG] 削除されたチャンク数: {cursor.rowcount}")
                
                # 新しいチャンクを挿入
                logger.info(f"[DEBUG] 新しいチャンク挿入開始")
                for i, chunk in enumerate(chunks):
                    logger.info(f"[DEBUG] チャンク {i+1}/{len(chunks)} 処理中: text長={len(chunk['text'])}, order={chunk['order']}, embedding長={len(chunk['embedding'])}")
                    
                    try:
                        # psycopg2でベクトルとJSONBを挿入
                        cursor.execute(
                            """
                            INSERT INTO document_chunks (document_id, chunk_text, chunk_order, embedding, chunk_metadata)
                            VALUES (%s, %s, %s, %s::vector, %s)
                            """,
                            (
                                document_id,
                                chunk['text'],
                                chunk['order'],
                                chunk['embedding'],  # リストのまま渡す
                                Json(chunk.get('metadata', {}))  # psycopg2.extras.Json()を使用
                            )
                        )
                        logger.info(f"[DEBUG] チャンク {i+1} 挿入成功: rowcount={cursor.rowcount}")
                        
                    except Exception as chunk_error:
                        logger.error(f"[DEBUG] チャンク {i+1} 挿入エラー: {chunk_error}")
                        raise chunk_error
                
                # コミット
                logger.info(f"[DEBUG] 全チャンク挿入完了、コミット実行")
                connection.commit()
                
                # 確認クエリ
                cursor.execute(
                    "SELECT COUNT(*) FROM document_chunks WHERE document_id = %s",
                    (document_id,)
                )
                actual_count = cursor.fetchone()[0]
                logger.info(f"[DEBUG] 保存後の確認: document_id={document_id}のチャンク数={actual_count}")
                
                logger.info(f"チャンク保存成功: ドキュメント {document_id}, {len(chunks)}チャンク")
                return {
                    "success": True,
                    "chunks_stored": len(chunks),
                    "message": "チャンクとベクトルが保存されました"
                }
                
            except Exception as e:
                logger.error(f"[DEBUG] チャンク保存エラー発生、ロールバック実行")
                connection.rollback()
                raise e
                
            finally:
                cursor.close()
                connection.close()
            
        except Exception as e:
            logger.error(f"チャンク保存エラー: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"エラー詳細: {traceback.format_exc()}")
            return {"success": False, "message": f"チャンク保存に失敗しました: {str(e)}"}
        finally:
            db.close()
    
    async def _vector_search(self, query_embedding: List[float], limit: int = 10, 
                          project_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """ベクトル類似検索を実行（psycopg2を直接使用）"""
        db = SessionLocal()
        try:
            # SQLAlchemy接続から生のpsycopg2接続を取得
            connection = db.get_bind().raw_connection()
            cursor = connection.cursor()
            
            try:
                # ベースクエリ（pgvectorの正しい構文を使用）
                base_query = """
                    SELECT dc.chunk_id, dc.document_id, dc.chunk_text, dc.chunk_metadata,
                           d.file_name, d.source_type, d.project_id,
                           (dc.embedding <-> %s::vector) as distance
                    FROM document_chunks dc
                    JOIN documents d ON dc.document_id = d.document_id
                """
                
                # ベクトルをpostgresのvector表現に変換
                vector_str = '[' + ','.join(map(str, query_embedding)) + ']'
                params = [vector_str]
                
                # プロジェクト絞り込み
                if project_id is not None:
                    base_query += " WHERE d.project_id = %s"
                    params.append(project_id)
                
                # 類似度順でソート・制限
                base_query += " ORDER BY distance ASC LIMIT %s"
                params.append(limit)
                
                cursor.execute(base_query, params)
                results = cursor.fetchall()
            
                # 結果を整形
                search_results = []
                for result in results:
                    search_results.append({
                        "chunk_id": result[0],
                        "document_id": result[1],
                        "document_name": result[4],
                        "chunk_text": result[2],
                        "similarity_score": 1.0 - result[7],  # 距離を類似度スコアに変換
                        "source_type": result[5],
                        "project_id": result[6],
                        "metadata": result[3] if result[3] else {}
                    })
                
                logger.info(f"ベクトル検索実行: {len(search_results)}件の結果")
                return search_results
                
            finally:
                cursor.close()
                connection.close()
            
        except Exception as e:
            logger.error(f"ベクトル検索エラー: {e}")
            return []
        finally:
            db.close()
    
    def _build_canvas_generation_prompt(self) -> str:
        """キャンバス生成用のシステムプロンプト"""
        return """
あなたは新規事業開発の専門家です。提供されたアイデアから、リーンキャンバスの11要素を生成してください。

リーンキャンバスの11要素：
1. 課題 (Problem): 解決すべき顧客の問題
2. 顧客セグメント (Customer Segments): ターゲット顧客
3. 独自の価値提案 (Unique Value Proposition): 競合との差別化要因
4. ソリューション (Solution): 問題を解決する方法
5. チャネル (Channels): 顧客にリーチする方法
6. 収益の流れ (Revenue Streams): 収益化の方法
7. コスト構造 (Cost Structure): 主要なコスト要因
8. 主要指標 (Key Metrics): 成功を測る指標
9. 圧倒的優位性 (Unfair Advantage): 模倣困難な競争優位
10. 早期アダプター (Early Adopters): 最初の顧客
11. 既存の代替 (Existing Alternatives): 現在の解決方法

各要素について、具体的で実用的な内容を提案してください。
回答は以下の形式で出力してください：

【課題】
[内容]

【顧客セグメント】
[内容]

【独自の価値提案】
[内容]

...（以下同様）
"""
    
    def _build_user_canvas_prompt(self, idea: str, audience: Optional[str], industry: Optional[str]) -> str:
        """ユーザー入力からキャンバス生成プロンプトを構築"""
        prompt = f"事業アイデア: {idea}\n"
        if audience:
            prompt += f"想定顧客: {audience}\n"
        if industry:
            prompt += f"業界: {industry}\n"
        prompt += "\n上記の情報を基に、リーンキャンバスの11要素を具体的に提案してください。"
        return prompt
    
    def _parse_canvas_response(self, response: str) -> Dict[str, str]:
        """AIレスポンスからキャンバスデータを解析"""
        canvas_data = {}
        field_mapping = {
            "課題": "problem",
            "顧客セグメント": "customer_segments",
            "独自の価値提案": "unique_value_proposition",
            "ソリューション": "solution",
            "チャネル": "channels",
            "収益の流れ": "revenue_streams",
            "コスト構造": "cost_structure",
            "主要指標": "key_metrics",
            "圧倒的優位性": "unfair_advantage",
            "早期アダプター": "early_adopters",
            "既存の代替": "existing_alternatives"
        }
        
        current_field = None
        current_content = []
        
        for line in response.split('\n'):
            line = line.strip()
            if line.startswith('【') and line.endswith('】'):
                # 前のフィールドを保存
                if current_field and current_content:
                    canvas_data[current_field] = '\n'.join(current_content).strip()
                
                # 新しいフィールド開始
                field_name = line[1:-1]  # 【】を除去
                current_field = field_mapping.get(field_name)
                current_content = []
            elif current_field and line:
                current_content.append(line)
        
        # 最後のフィールドを保存
        if current_field and current_content:
            canvas_data[current_field] = '\n'.join(current_content).strip()
        
        return canvas_data