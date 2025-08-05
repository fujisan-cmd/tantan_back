# リサーチ・インタビュー関連のPydanticモデル
from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum

class InterviewType(str, Enum):
    """インタビュータイプの列挙型"""
    HYPOTHESIS_TESTING = "hypothesis_testing"
    DEEP_DIVE = "deep_dive"

class ResearchRequest(BaseModel):
    """リサーチリクエストモデル"""
    research_focus: Optional[str] = Field(None, description="リサーチの焦点・目的")
    target_fields: Optional[List[str]] = Field(None, description="対象フィールド")

class ResearchResponse(BaseModel):
    """リサーチレスポンスモデル"""
    research_id: int
    result_text: str
    source_summary: str
    researched_at: datetime
    proposed_changes: Dict[str, str]  # フィールド名: 提案内容

class ResearchListItem(BaseModel):
    """リサーチ結果一覧項目モデル"""
    research_id: int
    researched_at: datetime
    result_summary: str  # 結果の要約（最初の100文字程度）
    source_summary: str

class InterviewPreparationRequest(BaseModel):
    """インタビュー準備リクエストモデル"""
    interview_purpose: str = Field(..., min_length=10, max_length=500)
    target_persona: Optional[str] = None
    focus_areas: Optional[List[str]] = None

class InterviewPreparationResponse(BaseModel):
    """インタビュー準備レスポンスモデル"""
    interview_questions: List[str]
    target_personas: List[str]
    preparation_tips: List[str]
    focus_areas: List[str]

class InterviewNoteCreate(BaseModel):
    """インタビューメモ作成用モデル"""
    interviewee_name: str = Field(..., min_length=1, max_length=255)
    interview_date: date
    interview_type: InterviewType
    interview_note: str = Field(..., min_length=10)

class InterviewNoteUpdate(BaseModel):
    """インタビューメモ更新用モデル"""
    interviewee_name: Optional[str] = Field(None, min_length=1, max_length=255)
    interview_date: Optional[date] = None
    interview_type: Optional[InterviewType] = None
    interview_note: Optional[str] = Field(None, min_length=10)

class InterviewNoteResponse(BaseModel):
    """インタビューメモレスポンスモデル"""
    note_id: int
    interviewee_name: str
    interview_date: date
    interview_type: str
    interview_note: str
    created_at: datetime
    user_email: str
    version: Optional[int] = None  # 関連するキャンバスバージョン

class InterviewNoteListResponse(BaseModel):
    """インタビューメモ一覧レスポンスモデル"""
    notes: List[InterviewNoteResponse]
    total_count: int

class InterviewToCanvasRequest(BaseModel):
    """インタビューメモのキャンバス反映リクエストモデル"""
    note_id: int
    target_fields: Optional[List[str]] = None  # 反映対象フィールド
    reflection_comment: Optional[str] = None

class InterviewReflectionResponse(BaseModel):
    """インタビュー反映レスポンスモデル"""
    current_canvas: Dict[str, str]
    proposed_canvas: Dict[str, str]
    extracted_insights: List[str]
    field_mappings: Dict[str, str]  # インサイト: 対象フィールド
    confidence_scores: Dict[str, float]  # フィールド名: 信頼度スコア