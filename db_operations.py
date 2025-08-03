# CRUD操作とモデル定義
from sqlalchemy import Column, Integer, String, VARCHAR, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from connect_PostgreSQL import Base, SessionLocal, engine
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import bcrypt
import secrets
import logging


logger = logging.getLogger(__name__)

# === SQLAlchemyモデル ===

class User(Base):
    """ユーザーテーブル"""
    __tablename__ = 'users'

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(VARCHAR(255), unique=True, nullable=False)
    hashed_pw: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow(), nullable=True)
    failed_login_counts: Mapped[int] = mapped_column(Integer, default=0)
    lock_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class Session(Base):
    """セッションテーブル"""
    __tablename__ = 'sessions'
    
    session_id = Column(String(255), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", backref="sessions")

class Project(Base):
    """プロジェクトテーブル"""
    __tablename__ = 'projects'
    
    project_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    project_name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    
    user = relationship("User", backref="projects")

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
        password_hash = hash_password(password)
        
        # 新規ユーザー作成
        new_user = User(
            email=email,
            hashed_password=password_hash
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
        if not verify_password(password, user.hashed_password):
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
