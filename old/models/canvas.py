# リーンキャンバス関連のPydanticモデル
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

class UpdateCategory(str, Enum):
    """更新カテゴリの列挙型"""
    MANUAL = "manual"
    CONSISTENCY_CHECK = "consistency_check"
    RESEARCH = "research"
    INTERVIEW = "interview"
    ROLLBACK = "rollback"

class LeanCanvasFields(BaseModel):
    """リーンキャンバスの11フィールド"""
    problem: Optional[str] = Field(None, description="課題")
    customer_segments: Optional[str] = Field(None, description="顧客セグメント")
    unique_value_proposition: Optional[str] = Field(None, description="独自の価値提案")
    solution: Optional[str] = Field(None, description="ソリューション")
    channels: Optional[str] = Field(None, description="チャネル")
    revenue_streams: Optional[str] = Field(None, description="収益の流れ")
    cost_structure: Optional[str] = Field(None, description="コスト構造")
    key_metrics: Optional[str] = Field(None, description="主要指標")
    unfair_advantage: Optional[str] = Field(None, description="圧倒的優位性")
    early_adopters: Optional[str] = Field(None, description="早期アダプター")
    existing_alternatives: Optional[str] = Field(None, description="既存の代替")

class ProjectCreate(BaseModel):
    """プロジェクト作成用モデル"""
    project_name: str = Field(..., min_length=1, max_length=255)
    canvas_data: LeanCanvasFields
    update_comment: Optional[str] = None

class ProjectUpdate(BaseModel):
    """プロジェクト更新用モデル"""
    canvas_data: LeanCanvasFields
    update_comment: Optional[str] = None
    update_category: UpdateCategory = UpdateCategory.MANUAL

class ProjectResponse(BaseModel):
    """プロジェクトレスポンスモデル"""
    project_id: int
    project_name: str
    user_id: int
    created_at: datetime
    current_version: int
    canvas_data: LeanCanvasFields
    last_updated: datetime
    update_category: str
    update_comment: Optional[str] = None

class ProjectListItem(BaseModel):
    """プロジェクト一覧用モデル"""
    project_id: int
    project_name: str
    created_at: datetime
    last_updated: datetime
    current_version: int

class EditHistoryItem(BaseModel):
    """編集履歴項目モデル"""
    edit_id: int
    version: int
    last_updated: datetime
    update_category: str
    update_comment: Optional[str] = None
    user_email: str

class CanvasAutoGenerateRequest(BaseModel):
    """キャンバス自動生成リクエストモデル"""
    idea_description: str = Field(..., min_length=10, max_length=2000)
    target_audience: Optional[str] = None
    industry: Optional[str] = None

class CanvasComparisonResponse(BaseModel):
    """キャンバス比較レスポンスモデル"""
    current_canvas: LeanCanvasFields
    proposed_canvas: LeanCanvasFields
    differences: Dict[str, Dict[str, Any]]  # フィールド名: {"current": str, "proposed": str, "changed": bool}

class RollbackRequest(BaseModel):
    """ロールバックリクエストモデル"""
    rollback_comment: Optional[str] = None