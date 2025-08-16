# CRUD操作とモデル定義
from sqlalchemy import Column, Integer, Text, VARCHAR, DateTime, Date, Boolean, JSON, ForeignKey
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import select, insert, update, delete
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from connect_PostgreSQL import SessionLocal, engine
from pydantic import BaseModel, EmailStr, Field, computed_field
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List, Dict, Any
from enum import Enum
import bcrypt
import secrets
import logging


logger = logging.getLogger(__name__)

# === SQLAlchemyモデル ===
class UpdateCategory(Enum):
    manual = 'manual'
    consistency_check = 'consistency_check'
    research = 'research'
    interview = 'interview'
    rollback = 'rollback'

class Role(Enum):
    admin = 'admin'
    editor = 'editor'

class InterviewType(Enum):
    hypothesis_testing = 'hypothesis_testing'
    deep_dive = 'deep_dive'
    CPF = 'CPF'
    PSF = 'PSF'

class SourceType(Enum):
    customer = 'customer'
    company = 'company'
    competitor = 'competitor'
    macrotrend = 'macrotrend'

class Base(DeclarativeBase):
    pass

class User(Base):
    """ユーザーテーブル"""
    __tablename__ = 'users'

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(VARCHAR(50), unique=True, nullable=False)
    hashed_pw: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failed_login_counts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lock_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    company_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

class Session(Base):
    """セッションテーブル"""
    __tablename__ = 'sessions'

    session_id: Mapped[str] = mapped_column(VARCHAR(255), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.user_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow() + timedelta(days=1), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user = relationship("User", backref="sessions")

class Project(Base):
    """プロジェクトテーブル"""
    __tablename__ = 'projects'

    project_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.user_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    project_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    
    user = relationship("User", backref="projects")

class EditHistory(Base):
    """編集履歴テーブル"""
    __tablename__ = 'edit_history'
    
    edit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey('projects.project_id'), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.user_id'), nullable=False)
    update_category: Mapped[UpdateCategory] = mapped_column(SQLEnum(UpdateCategory), nullable=False)
    update_comment: Mapped[Optional[str]] = mapped_column(VARCHAR(255), nullable=True)

    project = relationship("Project", backref="edit_history")
    user = relationship("User", backref="edit_history")

class Detail(Base):
    """詳細情報テーブル"""
    __tablename__ = 'details'
    
    edit_id: Mapped[int] = mapped_column(Integer, ForeignKey('edit_history.edit_id'), primary_key=True)
    field: Mapped[dict] = mapped_column(JSON, nullable=False)

    edit_history = relationship("EditHistory", backref="details")

class ProjectMember(Base):
    """プロジェクトメンバー"""
    __tablename__ = 'project_members'

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey('projects.project_id'), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.user_id'), primary_key=True) # 複合キー
    role: Mapped[Role] = mapped_column(SQLEnum(Role), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    project = relationship("Project", backref="project_members")
    user = relationship("User", backref="project_memberships")

class ResearchResult(Base):
    """リサーチ結果"""
    __tablename__ = 'research_results'

    research_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    edit_id: Mapped[int] = mapped_column(Integer, ForeignKey('edit_history.edit_id'), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.user_id'), nullable=False)
    researched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    result_text: Mapped[str] = mapped_column(Text, nullable=False)

    edit_history = relationship("EditHistory", backref="research_results")
    user = relationship("User", backref="research_results")

class InterviewNote(Base):
    """インタビュー結果"""
    __tablename__ = 'interview_notes'

    note_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    edit_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('edit_history.edit_id', ondelete="CASCADE"), nullable=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey('projects.project_id', ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.user_id', ondelete="CASCADE"), nullable=False)
    interviewee_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    interview_date: Mapped[date] = mapped_column(Date, nullable=False)
    interview_type: Mapped[InterviewType] = mapped_column(SQLEnum(InterviewType), nullable=False)
    interview_note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    edit_history = relationship("EditHistory", backref="interview_notes")
    project = relationship("Project", backref="interview_notes")
    user = relationship("User", backref="interview_notes")

class Document(Base):
    """投稿資料の情報"""
    __tablename__ = 'documents'

    document_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.user_id'), nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey('projects.project_id'), nullable=False)
    file_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(VARCHAR(500), nullable=True)
    file_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)  # 例: 'pdf', 'image', 'text'
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_type: Mapped[SourceType] = mapped_column(SQLEnum(SourceType), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    processing_status: Mapped[str] = mapped_column(
        VARCHAR(20),
        default='pending',
        nullable=False,
        server_default='pending',
    )

    user = relationship("User", backref="documents")
    project = relationship("Project", backref="documents")

# === Pydanticモデル ===

class UserCreate(BaseModel):
    """新規ユーザー登録用モデル"""
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    """ログイン用モデル"""
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    """ユーザー情報レスポンスモデル"""
    user_id: int
    email: str
    created_at: datetime
    last_login: Optional[datetime] = None

class ProjectResponse(BaseModel):
    """プロジェクトレスポンスモデル"""
    project_id: int
    project_name: str
    created_at: datetime

class AuthResponse(BaseModel):
    """認証レスポンスモデル"""
    message: str
    user: Optional[UserResponse] = None

class ProjectCreateRequest(BaseModel):
    user_id: int
    project_name: str
    field: Dict[str, Any]

class ProjectWithAI(BaseModel):
    idea_draft: str

class ProjectUpdateRequest(BaseModel):
    project_id: int
    user_id: int
    update_comment: str
    field: Dict[str, Any]

# === CRUD関数 ===

def hash_password(password: str) -> str:
    """パスワードをハッシュ化"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    """パスワードを検証"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_user(email: str, password: str) -> Dict[str, Any]:
    """新規ユーザー作成"""
    db = SessionLocal()
    try:
        # パスワードの基本検証
        if len(password) < 8:
            return {"success": False, "message": "パスワードは8文字以上で入力してください"}
        
        # 既存ユーザーチェック
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            return {"success": False, "message": "このメールアドレスは既に登録されています"}
        
        # パスワードハッシュ化
        hashed_pw = hash_password(password)
        
        # 新規ユーザー作成
        new_user = User(
            email=email,
            hashed_pw=hashed_pw
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"新規ユーザー作成成功: {email}")
        return {
            "success": True,
            "message": "ユーザー登録が完了しました",
            "user_id": new_user.user_id
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"ユーザー作成エラー: {e}")
        return {"success": False, "message": "ユーザー作成に失敗しました"}
    finally:
        db.close()

def authenticate_user(email: str, password: str) -> Dict[str, Any]:
    """ユーザー認証"""
    db = SessionLocal()
    try:
        # ユーザー取得
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return {"success": False, "message": "メールアドレスが正しくありません"}
        
        # パスワード検証
        if not verify_password(password, user.hashed_pw):
            return {"success": False, "message": "パスワードが正しくありません"}
        
        # 最終ログイン時刻更新
        user.last_login = func.now()
        db.commit()
        
        logger.info(f"ユーザー認証成功: {email}")
        return {
            "success": True,
            "message": "認証成功",
            "user_id": user.user_id,
            "email": user.email
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"認証エラー: {e}")
        return {"success": False, "message": "認証に失敗しました"}
    finally:
        db.close()

def create_session(user_id: int) -> Optional[str]:
    """セッション作成"""
    db = SessionLocal()
    try:
        # セッションID生成
        session_id = secrets.token_urlsafe(32)
        
        # セッション作成（24時間有効）
        from datetime import timedelta
        expires_at = datetime.utcnow() + timedelta(hours=24)
        
        new_session = Session(
            session_id=session_id,
            user_id=user_id,
            expires_at=expires_at
        )
        
        db.add(new_session)
        db.commit()
        
        logger.info(f"セッション作成成功: user_id={user_id}")
        return session_id
        
    except Exception as e:
        db.rollback()
        logger.error(f"セッション作成エラー: {e}")
        return None
    finally:
        db.close()

def validate_session(session_id: str) -> Optional[int]:
    """セッション検証"""
    db = SessionLocal()
    try:
        session = db.query(Session).filter(
            Session.session_id == session_id,
            Session.is_active == True,
            Session.expires_at > datetime.utcnow()
        ).first()
        
        if session:
            return session.user_id
        return None
        
    except Exception as e:
        logger.error(f"セッション検証エラー: {e}")
        return None
    finally:
        db.close()

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """ユーザー情報取得"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if user:
            return {
                "user_id": user.user_id,
                "email": user.email,
                "created_at": user.created_at,
                "last_login": user.last_login
            }
        return None
        
    except Exception as e:
        logger.error(f"ユーザー取得エラー: {e}")
        return None
    finally:
        db.close()

def get_user_projects(user_id: int) -> List[Dict[str, Any]]:
    """ユーザーのプロジェクト一覧取得"""
    db = SessionLocal()
    try:
        projects = db.query(Project).filter(
            Project.user_id == user_id
        ).all()
        
        return [
            {
                "project_id": project.project_id,
                "project_name": project.project_name,
                "created_at": project.created_at
            }
            for project in projects
        ]
        
    except Exception as e:
        logger.error(f"プロジェクト取得エラー: {e}")
        return []
    finally:
        db.close()

def get_project_by_id(project_id: int) -> Optional[Dict[str, Any]]:
    """指定されたプロジェクトIDのプロジェクト情報を取得"""
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.project_id == project_id).first()
        
        if project:
            return {
                "project_id": project.project_id,
                "project_name": project.project_name,
                "user_id": project.user_id,
                "created_at": project.created_at
            }
        return None
        
    except Exception as e:
        logger.error(f"プロジェクト取得エラー: {e}")
        return None
    finally:
        db.close()

# テーブル作成
def create_tables():
    """テーブル作成"""
    Base.metadata.create_all(bind=engine)
    logger.info("テーブル作成完了")


def get_latest_edit_id(project_id: int) -> Optional[int]:
    """指定されたプロジェクトの最新のedit_idを取得"""
    db = SessionLocal()
    query = select(EditHistory).filter(
        EditHistory.project_id == project_id
            ).order_by(EditHistory.last_updated.desc()).limit(1)

    try:
        with db.begin():
            result = db.execute(query).scalar_one_or_none()
            if result:
                return result.edit_id
            return None
        
    except Exception as e:
        logger.error(f"最新のedit_id取得エラー: {e}")
        return None

def get_canvas_details(edit_id: int) -> Optional[Dict[str, Any]]:
    """指定されたedit_idのキャンバス詳細を取得"""
    db = SessionLocal()
    query = select(Detail).filter(Detail.edit_id == edit_id)

    try:
        with db.begin():
            result = db.execute(query).scalars().all()
            if not result:
                return None
            
            details = {detail.edit_id: detail.field for detail in result}
            return details
        
    except Exception as e:
        logger.error(f"キャンバス詳細取得エラー: {e}")
        return None
    
def insert_project(value):
    """プロジェクトを挿入"""
    db = SessionLocal()
    query = insert(Project).values(value)
    try:
        with db.begin():
            result = db.execute(query)
            project_id = result.inserted_primary_key[0]
            logger.info(f"プロジェクト挿入成功: project_id={project_id}")
            return project_id
    except Exception as e:
        db.rollback()
        logger.error(f"プロジェクト挿入エラー: {e}")
        return None
    finally:
        db.close()

def insert_edit_history(project_id: int, version: int, user_id: int, update_category: UpdateCategory, update_comment: Optional[str]) -> int:
    """プロジェクトの編集履歴を挿入"""
    db = SessionLocal()

    values = {
        "project_id": project_id,
        "version": version,
        "user_id": user_id,
        "update_category": update_category,
    }
    if update_comment:
        values["update_comment"] = update_comment
    query = insert(EditHistory).values(values)
    try:
        with db.begin():
            result = db.execute(query)
            edit_id = result.inserted_primary_key[0]
            logger.info(f"編集履歴挿入成功: edit_id={edit_id}, project_id={project_id}")
            return edit_id
    except Exception as e:
        db.rollback()
        logger.error(f"編集履歴挿入エラー: {e}")
        return 0
    finally:
        db.close()

def insert_canvas_details(edit_id: int, field: Dict[str, Any]) -> bool:
    """キャンバスの詳細情報を挿入"""
    db = SessionLocal()
    query = insert(Detail).values(edit_id=edit_id, field=field)
    try:
        with db.begin():
            result = db.execute(query)
            detail_id = result.inserted_primary_key[0]
            logger.info(f"キャンバス詳細挿入成功: detail_id={detail_id}, edit_id={edit_id}")
            return True
    except Exception as e:
        db.rollback()
        logger.error(f"キャンバス詳細挿入エラー: {e}")
        return False
    finally:
        db.close()

def get_latest_version(project_id: int):
    db = SessionLocal()
    query = select(EditHistory).filter(
        EditHistory.project_id == project_id
            ).order_by(EditHistory.last_updated.desc()).limit(1)

    try:
        with db.begin():
            result = db.execute(query).scalars().first()
            if result:
                return result.version
            return None

    except Exception as e:
        logger.error(f"最新のバージョン取得エラー: {e}")
        return None
    
def get_project_documents(project_id: int) -> List[Dict[str, Any]]:
    """指定されたプロジェクトの文書一覧取得"""
    db = SessionLocal()
    try:
        documents = db.query(Document).filter(
            Document.project_id == project_id
        ).order_by(Document.uploaded_at.desc()).all()

        return [
            {
                "document_id": doc.document_id,
                "file_name": doc.file_name,
                "file_type": doc.file_type,
                "source_type": doc.source_type.value,  # Enumなら .value
                "uploaded_at": doc.uploaded_at,
            }
            for doc in documents
        ]
    except Exception as e:
        logger.error(f"プロジェクト文書取得エラー: {e}")
        return []
    finally:
        db.close()

def record_consistency_check(project_id: int, user_id: int, analysis_result: Dict[str, str]) -> bool:
    """整合性確認の結果をデータベースに記録"""
    try:
        with SessionLocal() as session:
            # 最新のバージョンを取得
            latest_edit = session.query(EditHistory).filter(
                EditHistory.project_id == project_id
            ).order_by(EditHistory.version.desc()).first()
            
            if latest_edit:
                new_version = latest_edit.version + 1
            else:
                new_version = 1
            
            # 編集履歴を作成
            edit_history = EditHistory(
                project_id=project_id,
                version=new_version,
                user_id=user_id,
                update_category=UpdateCategory.consistency_check,
                update_comment="AI整合性確認による改善提案"
            )
            session.add(edit_history)
            session.flush()  # edit_idを取得するためにflush
            
            # 分析結果をJSONフィールドに保存
            analysis_field = {
                "consistency_analysis": analysis_result,
                "analysis_type": "consistency_check",
                "analyzed_at": datetime.now().isoformat()
            }
            
            canvas_detail = Detail(
                edit_id=edit_history.edit_id,
                field=analysis_field
            )
            session.add(canvas_detail)
            session.commit()
            
            logger.info(f"整合性確認結果を記録しました: project_id={project_id}, edit_id={edit_history.edit_id}")
            return True
            
    except Exception as e:
        logger.error(f"整合性確認結果の記録エラー: {e}")
        return False

def insert_research_result(edit_id: int, user_id: int, result_text: str) -> bool:
    db = SessionLocal()
    query = insert(ResearchResult).values(edit_id=edit_id, user_id=user_id, result_text=result_text)
    try:
        with db.begin():
            result = db.execute(query)
            research_id = result.inserted_primary_key[0]
            logger.info(f"リサーチ結果挿入成功: research_id={research_id}, edit_id={edit_id}")
            return True
    except Exception as e:
        db.rollback()
        logger.error(f"リサーチ結果挿入エラー: {e}")
        return False
    finally:
        db.close()

def get_all_interview_notes(project_id: int):
    db = SessionLocal()
    query = select(
        InterviewNote.interviewee_name,
        InterviewNote.interview_date,
        InterviewNote.user_id,
        InterviewNote.edit_id,
        EditHistory.version,
        User.email,
        InterviewNote.interview_note,
        InterviewNote.interview_type,
    )\
    .join(EditHistory, InterviewNote.edit_id == EditHistory.edit_id, isouter=True)\
    .join(User, InterviewNote.user_id == User.user_id, isouter=True)\
    .filter(InterviewNote.project_id == project_id)
    try:
        with db.begin():
            rows = db.execute(query).all()
            if not rows:
                return None
            
            result = []
            for name, idate, user_id, edit_id, version, email, interview_note, interview_type in rows:
                result.append({
                    "interviewee_name": name,
                    "interview_date": idate,
                    "user_id": user_id,
                    "edit_id": edit_id,
                    "version": version,
                    "email": email,
                    "interview_note": interview_note,
                    "interview_type": interview_type,
                })
            return result
    finally:
        db.close()

# === RAG機能用追加 START ===
# 注意: データベーススキーマ適用前のため一時的にコメントアウト

# class Document(Base):
#     """ドキュメントテーブル（RAG対応）"""
#     __tablename__ = 'documents'
# 
#     document_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.user_id'), nullable=False)
#     project_id: Mapped[int] = mapped_column(Integer, ForeignKey('projects.project_id'), nullable=False)
#     file_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
#     file_path: Mapped[Optional[str]] = mapped_column(VARCHAR(500), nullable=True)  # RAG: NULL許可
#     file_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
#     file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
#     source_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
#     uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
#     processing_status: Mapped[str] = mapped_column(VARCHAR(20), default='pending', nullable=False)
# 
#     user = relationship("User", backref="documents")
#     project = relationship("Project", backref="documents")

class DocumentChunk(Base):
    """ドキュメントチャンクテーブル（RAG用ベクトル保存）"""
    __tablename__ = 'document_chunks'

    chunk_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(Integer, ForeignKey('documents.document_id'), nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_order: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # pgvector型（文字列として扱う）
    chunk_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    document = relationship("Document", backref="chunks")

# RAG機能用Pydanticモデル
class DocumentUploadResponse(BaseModel):
    document_id: int
    file_name: str
    file_type: str
    file_size: int
    processing_status: str
    chunks_count: Optional[int] = 0
    created_at: datetime

class TextDocumentResponse(BaseModel):
    document_id: int
    file_name: str
    file_type: str
    source_type: str
    text_preview: str
    processing_status: str
    chunks_count: int
    uploaded_at: datetime

class SearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 10

class SearchResult(BaseModel):
    chunk_text: str
    similarity_score: float
    document_name: str
    source_type: str

class CanvasGenerationRequest(BaseModel):
    idea_description: str
    target_audience: Optional[str] = None
    industry: Optional[str] = None

class ConsistencyCheckRequest(BaseModel):
    """リーンキャンバス整合性確認リクエストモデル（現在は空、将来の拡張用）"""
    pass

class ConsistencyCheckResponse(BaseModel):
    """リーンキャンバス整合性確認レスポンスモデル"""
    success: bool
    analysis: Optional[Dict[str, Dict[str, str]]] = None
    analyzed_at: Optional[str] = None
    
    @computed_field
    @property
    def message(self) -> Optional[str]:
        """エラーメッセージ（エラー時のみ）"""
        return None if self.success else "エラーが発生しました"

class AutoAnswerGenerationRequest(BaseModel):
    """AI回答自動生成リクエストモデル"""
    project_id: int
    questions: List[Dict[str, Any]]  # 質問とその内容

class AutoAnswerGenerationResponse(BaseModel):
    """AI回答自動生成レスポンスモデル"""
    success: bool
    answers: Optional[List[str]] = None
    generated_at: Optional[str] = None
    
    @computed_field
    @property
    def message(self) -> Optional[str]:
        """エラーメッセージ（エラー時のみ）"""
        return None if self.success else "エラーが発生しました"

class CanvasUpdateRequest(BaseModel):
    """リーンキャンバス更新案生成リクエストモデル"""
    project_id: int
    user_answers: List[Dict[str, Any]]  # ユーザーの回答内容

class CanvasUpdateResponse(BaseModel):
    """リーンキャンバス更新案生成レスポンスモデル"""
    success: bool
    updated_canvas: Optional[Dict[str, Any]] = None
    generated_at: Optional[str] = None
    
    @computed_field
    @property
    def message(self) -> Optional[str]:
        """エラーメッセージ（エラー時のみ）"""
        return None if self.success else "エラーが発生しました"

# RAG機能用CRUD関数
def create_document_record(user_id: int, project_id: int, file_name: str, 
                          file_type: str, file_size: int, source_type: str) -> Optional[int]:
    """ドキュメント記録を作成"""
    db = SessionLocal()
    try:
        new_doc = Document(
            user_id=user_id,
            project_id=project_id,
            file_name=file_name,
            file_type=file_type,
            file_size=file_size,
            source_type=source_type,
            processing_status='pending'
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        
        logger.info(f"ドキュメント記録作成成功: {file_name} (ID: {new_doc.document_id})")
        return new_doc.document_id
        
    except Exception as e:
        db.rollback()
        logger.error(f"ドキュメント記録作成エラー: {e}")
        return None
    finally:
        db.close()

# def update_document_processing_status(document_id: int, status: str) -> bool:
#     """ドキュメント処理状況を更新"""
#     db = SessionLocal()
#     try:
#         doc = db.query(Document).filter(Document.document_id == document_id).first()
#         if doc:
#             doc.processing_status = status
#             if status == 'completed':
#                 doc.file_path = None  # RAG処理完了後はfile_pathをクリア
#             db.commit()
#             logger.info(f"ドキュメント処理状況更新: {document_id} -> {status}")
#             return True
#         return False
#         
#     except Exception as e:
#         db.rollback()
#         logger.error(f"ドキュメント処理状況更新エラー: {e}")
#         return False
#     finally:
#         db.close()

# def get_project_documents(project_id: int, user_id: int) -> List[Dict[str, Any]]:
#     """プロジェクトのドキュメント一覧取得"""
#     db = SessionLocal()
#     try:
#         docs = db.query(Document).filter(
#             Document.project_id == project_id,
#             Document.user_id == user_id
#         ).order_by(Document.uploaded_at.desc()).all()
#         
#         result = []
#         for doc in docs:
#             # チャンク数を取得
#             chunk_count = db.query(DocumentChunk).filter(
#                 DocumentChunk.document_id == doc.document_id
#             ).count()
#             
#             result.append({
#                 "document_id": doc.document_id,
#                 "file_name": doc.file_name,
#                 "file_type": doc.file_type,
#                 "file_size": doc.file_size,
#                 "source_type": doc.source_type,
#                 "processing_status": doc.processing_status,
#                 "chunks_count": chunk_count,
#                 "uploaded_at": doc.uploaded_at
#             })
#         
#         return result
#         
#     except Exception as e:
#         logger.error(f"プロジェクトドキュメント取得エラー: {e}")
#         return []
#     finally:
#         db.close()

# def delete_document_record(document_id: int, user_id: int) -> bool:
#     """ドキュメント記録を削除"""
#     db = SessionLocal()
#     try:
#         doc = db.query(Document).filter(
#             Document.document_id == document_id,
#             Document.user_id == user_id
#         ).first()
#         
#         if doc:
#             # チャンクも一緒に削除される（CASCADE）
#             db.delete(doc)
#             db.commit()
#             logger.info(f"ドキュメント削除成功: {document_id}")
#             return True
#         return False
#         
#     except Exception as e:
#         db.rollback()
#         logger.error(f"ドキュメント削除エラー: {e}")
#         return False
#     finally:
#         db.close()

# === RAG機能用追加 END ===
