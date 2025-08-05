# RAG（Retrieval-Augmented Generation）サービス
import os
import openai
from typing import List, Dict, Any, Optional, Tuple
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
import tiktoken
import asyncio
import logging
from datetime import datetime

from crud.documents import VectorStoreCRUD
from database import db_connection

logger = logging.getLogger(__name__)

class RAGService:
    """RAG関連のビジネスロジック"""
    
    def __init__(self):
        # OpenAI設定
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("OPENAI_API_KEYが設定されていません")
        
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
        
        # データベースCRUD
        self.vector_crud = VectorStoreCRUD(db_connection)
    
    async def process_document_for_rag(self, document_id: int, text_content: str) -> Dict[str, Any]:
        """ドキュメントをRAG用に処理（チャンク化＋ベクトル化）"""
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
            result = await self.vector_crud.store_document_chunks(document_id, chunk_data)
            
            logger.info(f"ドキュメント処理完了: {document_id}, {len(chunk_data)}チャンク")
            return {
                "success": True,
                "chunks_processed": len(chunk_data),
                "total_tokens": sum(chunk["metadata"]["token_count"] for chunk in chunk_data),
                "message": "ドキュメントのRAG処理が完了しました"
            }
            
        except Exception as e:
            logger.error(f"ドキュメントRAG処理エラー: {e}")
            return {"success": False, "message": f"RAG処理に失敗しました: {str(e)}"}
    
    async def search_relevant_content(self, query: str, project_id: Optional[int] = None, 
                                    limit: int = 10, source_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """関連コンテンツを検索"""
        try:
            # クエリのベクトル埋め込みを生成
            query_embedding = await self._get_embedding(query)
            
            # ベクトル検索実行
            search_results = await self.vector_crud.vector_search(
                query_embedding=query_embedding,
                limit=limit,
                project_id=project_id,
                source_types=source_types
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
            
            # OpenAI APIを呼び出し
            response = await openai.ChatCompletion.acreate(
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
    
    async def research_and_enhance_canvas(self, current_canvas: Dict[str, Any], project_id: int,
                                        research_focus: Optional[str] = None) -> Dict[str, Any]:
        """既存のキャンバスをリサーチして改善提案を生成"""
        try:
            # 現在のキャンバス内容から検索クエリを生成
            search_queries = self._generate_search_queries(current_canvas, research_focus)
            
            # 関連コンテンツを検索
            all_relevant_content = []
            for query in search_queries:
                results = await self.search_relevant_content(query, project_id, limit=5)
                all_relevant_content.extend(results)
            
            if not all_relevant_content:
                return {
                    "success": False,
                    "message": "関連する情報が見つかりませんでした"
                }
            
            # 検索結果を要約
            content_summary = self._summarize_search_results(all_relevant_content)
            
            # 改善提案を生成
            enhancement_prompt = self._build_enhancement_prompt(current_canvas, content_summary, research_focus)
            
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=[
                    {"role": "system", "content": "あなたは新規事業開発の専門家です。提供された情報を基にリーンキャンバスの改善提案を行ってください。"},
                    {"role": "user", "content": enhancement_prompt}
                ],
                temperature=0.6,
                max_tokens=1500
            )
            
            enhancement_content = response.choices[0].message.content
            proposed_changes = self._parse_enhancement_response(enhancement_content)
            
            logger.info(f"キャンバス改善提案完了: プロジェクト={project_id}")
            return {
                "success": True,
                "proposed_changes": proposed_changes,
                "source_summary": content_summary,
                "research_queries": search_queries,
                "raw_response": enhancement_content,
                "message": "リサーチに基づく改善提案が生成されました"
            }
            
        except Exception as e:
            logger.error(f"キャンバス改善提案エラー: {e}")
            return {"success": False, "message": f"改善提案生成に失敗しました: {str(e)}"}
    
    async def analyze_interview_insights(self, interview_text: str, current_canvas: Dict[str, Any]) -> Dict[str, Any]:
        """インタビュー内容を分析してキャンバスへの反映提案を生成"""
        try:
            # インタビュー分析プロンプト構築
            analysis_prompt = self._build_interview_analysis_prompt(interview_text, current_canvas)
            
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=[
                    {"role": "system", "content": "あなたは顧客インタビューの分析専門家です。インタビュー内容から有用なインサイトを抽出し、リーンキャンバスへの反映提案を行ってください。"},
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=0.5,
                max_tokens=1200
            )
            
            analysis_content = response.choices[0].message.content
            insights_data = self._parse_interview_analysis(analysis_content)
            
            logger.info(f"インタビュー分析完了")
            return {
                "success": True,
                "insights": insights_data,
                "raw_analysis": analysis_content,
                "message": "インタビュー分析が完了しました"
            }
            
        except Exception as e:
            logger.error(f"インタビュー分析エラー: {e}")
            return {"success": False, "message": f"インタビュー分析に失敗しました: {str(e)}"}
    
    async def _get_embedding(self, text: str) -> List[float]:
        """テキストのベクトル埋め込みを取得"""
        try:
            # LangChainの埋め込みを使用
            embedding = await self.embeddings.aembed_query(text)
            return embedding
        except Exception as e:
            logger.error(f"埋め込み生成エラー: {e}")
            raise
    
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
    
    def _generate_search_queries(self, canvas: Dict[str, Any], focus: Optional[str]) -> List[str]:
        """キャンバス内容から検索クエリを生成"""
        queries = []
        
        if focus:
            queries.append(focus)
        
        # 主要フィールドからクエリを生成
        if canvas.get('problem'):
            queries.append(canvas['problem'][:100])
        if canvas.get('customer_segments'):
            queries.append(canvas['customer_segments'][:100])
        if canvas.get('solution'):
            queries.append(canvas['solution'][:100])
        
        return queries[:5]  # 最大5つのクエリ
    
    def _summarize_search_results(self, results: List[Dict[str, Any]]) -> str:
        """検索結果を要約"""
        if not results:
            return "関連情報が見つかりませんでした。"
        
        summary_parts = []
        for result in results[:10]:  # 上位10件
            summary_parts.append(f"出典: {result['document_name']}")
            summary_parts.append(f"内容: {result['chunk_text'][:200]}...")
            summary_parts.append("---")
        
        return '\n'.join(summary_parts)
    
    def _build_enhancement_prompt(self, canvas: Dict[str, Any], content_summary: str, focus: Optional[str]) -> str:
        """改善提案プロンプトを構築"""
        prompt = "現在のリーンキャンバス:\n"
        for field, value in canvas.items():
            if value:
                prompt += f"{field}: {value}\n"
        
        prompt += f"\n関連情報:\n{content_summary}\n"
        
        if focus:
            prompt += f"\n特に注目すべき点: {focus}\n"
        
        prompt += "\n上記の関連情報を基に、現在のキャンバスの改善提案を行ってください。"
        return prompt
    
    def _parse_enhancement_response(self, response: str) -> Dict[str, str]:
        """改善提案レスポンスを解析"""
        # 簡単な解析実装（実際にはより詳細な解析が必要）
        return {"enhancement_summary": response}
    
    def _build_interview_analysis_prompt(self, interview: str, canvas: Dict[str, Any]) -> str:
        """インタビュー分析プロンプトを構築"""
        prompt = f"インタビュー内容:\n{interview}\n\n"
        prompt += "現在のリーンキャンバス:\n"
        for field, value in canvas.items():
            if value:
                prompt += f"{field}: {value}\n"
        
        prompt += "\nインタビュー内容から有用なインサイトを抽出し、キャンバスへの反映提案を行ってください。"
        return prompt
    
    def _parse_interview_analysis(self, response: str) -> Dict[str, Any]:
        """インタビュー分析レスポンスを解析"""
        # 簡単な解析実装（実際にはより詳細な解析が必要）
        return {"analysis_summary": response}