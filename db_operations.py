# CRUD操作とモデル定義
from sqlalchemy import Column, Integer, Text, VARCHAR, DateTime, Date, Boolean, JSON, ForeignKey
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import select, insert, update, delete
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from connect_PostgreSQL import SessionLocal, engine
from pydantic import BaseModel, EmailStr
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
    field_name: Mapped[dict] = mapped_column(JSON, nullable=False)
    field_content: Mapped[dict] = mapped_column(JSON, nullable=False)

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
    result_text: Mapped[str] = mapped_column(VARCHAR(1000), nullable=False)

    edit_history = relationship("EditHistory", backref="research_results")
    user = relationship("User", backref="research_results")

class InterviewNote(Base):
    """インタビュー結果"""
    __tablename__ = 'interview_notes'

    note_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    edit_id: Mapped[int] = mapped_column(Integer, ForeignKey('edit_history.edit_id'), nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey('projects.project_id'), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.user_id'), nullable=False)
    interviewee_name: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    interview_date: Mapped[date] = mapped_column(Date, nullable=False)
    interview_type: Mapped[InterviewType] = mapped_column(SQLEnum(InterviewType), nullable=False)
    interview_note: Mapped[str] = mapped_column(Text, nullable=False)

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
    file_path: Mapped[str] = mapped_column(VARCHAR(500), nullable=False)
    file_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)  # 例: 'pdf', 'image', 'text'
    source_type: Mapped[SourceType] = mapped_column(SQLEnum(SourceType), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

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
    description: Optional[str]
    created_at: datetime

class AuthResponse(BaseModel):
    """認証レスポンスモデル"""
    message: str
    user: Optional[UserResponse] = None

class ProjectCreateRequest(BaseModel):
    user_id: int
    project_name: str
    field_name: Dict[str, Any]
    field_content: Dict[str, Any]

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
            return {"success": False, "message": "メールアドレスまたはパスワードが正しくありません"}
        
        # パスワード検証
        if not verify_password(password, user.hashed_pw):
            return {"success": False, "message": "メールアドレスまたはパスワードが正しくありません"}
        
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
            Project.user_id == user_id,
            Project.is_active == True
        ).all()
        
        return [
            {
                "project_id": project.project_id,
                "project_name": project.project_name,
                "description": project.description,
                "created_at": project.created_at
            }
            for project in projects
        ]
        
    except Exception as e:
        logger.error(f"プロジェクト取得エラー: {e}")
        return []
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
            result = db.execute(query).all()
            if not result:
                return None
            
            details = {detail.field_name: detail.field_content for detail in result}
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

def insert_edit_history(project_id: int, version: int, user_id: int, update_category: UpdateCategory) -> int:
    """プロジェクトの編集履歴を挿入"""
    db = SessionLocal()
    query = insert(EditHistory).values(project_id=project_id, version=version, user_id=user_id, update_category=update_category)
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

def insert_canvas_details(edit_id: int, field_name: Dict[str, Any], field_content: Dict[str, Any]) -> bool:
    """キャンバスの詳細情報を挿入"""
    db = SessionLocal()
    query = insert(Detail).values(edit_id=edit_id, field_name=field_name, field_content=field_content)
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
