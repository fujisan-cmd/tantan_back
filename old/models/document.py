# ドキュメント関連のPydanticモデル
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum

class SourceType(str, Enum):
    """ドキュメントソースタイプの列挙型"""
    CUSTOMER = "Customer"
    COMPANY = "Company"
    COMPETITOR = "Competitor"
    MACROTREND = "Macrotrend"

class DocumentUpload(BaseModel):
    """ドキュメントアップロード用モデル"""
    file_name: str = Field(..., min_length=1, max_length=255)
    source_type: SourceType
    file_size: Optional[int] = None

class DocumentResponse(BaseModel):
    """ドキュメントレスポンスモデル"""
    document_id: int
    file_name: str
    file_type: str
    file_size: Optional[int] = None
    source_type: str
    uploaded_at: datetime
    user_email: str

class DocumentListResponse(BaseModel):
    """ドキュメント一覧レスポンスモデル"""
    documents: List[DocumentResponse]
    total_count: int
    total_size: int  # バイト単位

class DocumentChunk(BaseModel):
    """ドキュメントチャンクモデル（内部使用）"""
    chunk_id: int
    document_id: int
    chunk_text: str
    chunk_order: int
    metadata: Optional[dict] = None

class VectorSearchRequest(BaseModel):
    """ベクトル検索リクエストモデル"""
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(10, ge=1, le=50)
    project_id: Optional[int] = None
    source_types: Optional[List[SourceType]] = None

class VectorSearchResult(BaseModel):
    """ベクトル検索結果モデル"""
    chunk_id: int
    document_id: int
    document_name: str
    chunk_text: str
    similarity_score: float
    source_type: str
    metadata: Optional[dict] = None

class VectorSearchResponse(BaseModel):
    """ベクトル検索レスポンスモデル"""
    results: List[VectorSearchResult]
    total_results: int
    query: str