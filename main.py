# Idea Spark - 新規事業開発支援WebアプリケーションのメインAPI
from fastapi import FastAPI, HTTPException, Depends, Cookie, Response, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from typing import Optional, List
from dotenv import load_dotenv
import logging
import os
import asyncio

# .envファイルを読み込み
load_dotenv()

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# モデルとサービスのインポート
from models import *
from services import auth_service, get_current_user, FileService, RAGService, CanvasService
from crud import UserCRUD, ProjectCRUD, DocumentCRUD, ResearchCRUD, InterviewCRUD
from database import db_connection, test_database_connection

app = FastAPI(
    title="Idea Spark API",
    description="新規事業開発支援WebアプリケーションのAPI",
    version="1.0.0"
)

# CORS設定（環境変数から取得、デフォルト値設定）
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001").split(",")
logger.info(f"CORS allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# サービスインスタンス
file_service = FileService()
rag_service = RAGService()
canvas_service = CanvasService()

# CRUDインスタンス
user_crud = UserCRUD(db_connection)
project_crud = ProjectCRUD(db_connection)
document_crud = DocumentCRUD(db_connection)
research_crud = ResearchCRUD(db_connection)
interview_crud = InterviewCRUD(db_connection)

# ===== 基本的なエンドポイント =====

@app.get("/")
async def read_root():
    return {"message": "Idea Spark API へようこそ！", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """基本ヘルスチェック"""
    return {"status": "OK", "service": "Idea Spark API"}

@app.get("/health/detailed")
async def detailed_health_check():
    """詳細ヘルスチェック - データベース接続も含む"""
    health_status = {
        "status": "OK",
        "service": "Idea Spark API",
        "database": "disconnected",
        "timestamp": datetime.now().isoformat(),
        "environment": {
            "allowed_origins": allowed_origins,
            "db_host": os.getenv("DB_HOST", "localhost"),
            "db_name": os.getenv("DB_NAME", "idea_spark")
        }
    }
    
    try:
        # PostgreSQL接続テスト
        db_test_result = await test_database_connection()
        health_status["database"] = db_test_result["status"]
        health_status["pgvector_enabled"] = db_test_result.get("pgvector_enabled", False)
        
        if db_test_result["status"] == "connected":
            logger.info("Database health check: OK")
        else:
            health_status["status"] = "DEGRADED"
            health_status["database_error"] = db_test_result.get("error")
            logger.error(f"Database health check failed: {db_test_result.get('error')}")
            
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "DEGRADED"
        logger.error(f"Database health check failed: {e}")
    
    return health_status

@app.get("/debug/info")
async def debug_info():
    """デバッグ情報（センシティブ情報は除外）"""
    import sys
    import platform
    
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "fastapi_version": "0.104.1",
        "environment_vars": {
            "ALLOWED_ORIGINS": os.getenv("ALLOWED_ORIGINS", "not_set"),
            "DB_HOST": os.getenv("DB_HOST", "not_set"),
            "DB_NAME": os.getenv("DB_NAME", "not_set"),
            "ENVIRONMENT": os.getenv("ENVIRONMENT", "not_set")
        },
        "current_working_directory": os.getcwd()
    }

@app.post("/api/signup/simple")
async def simple_signup(request: Request):
    """シンプルな新規登録テスト（フォールバック用）"""
    try:
        body = await request.json()
        email = body.get("email")
        password = body.get("password")
        
        if not email or not password:
            return {"success": False, "message": "メールアドレスとパスワードが必要です"}
        
        logger.info(f"Simple signup attempt: {email}")
        return {"success": True, "message": "シンプル登録テスト成功", "email": email}
    except Exception as e:
        logger.error(f"Simple signup error: {e}")
        return {"success": False, "message": f"エラー: {str(e)}"}

# ===== 認証関連エンドポイント =====

@app.post("/api/signup", response_model=AuthResponse)
async def signup(user_data: UserCreate, request: Request):
    """新規ユーザー登録"""
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"Signup attempt from {client_ip} for email: {user_data.email}")
    
    try:
        # AuthServiceを使用
        result = await auth_service.register_user(user_data.email, user_data.password)
        
        if result["success"]:
            logger.info(f"Successful signup for email: {user_data.email}")
            return AuthResponse(message=result["message"])
        else:
            logger.warning(f"Failed signup for email: {user_data.email} - {result['message']}")
            raise HTTPException(status_code=400, detail=result["message"])
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error for {user_data.email}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"サーバーエラーが発生しました: {str(e)}")

@app.post("/api/login", response_model=AuthResponse)
async def login(user_data: UserLogin, response: Response, request: Request):
    """ユーザーログイン"""
    try:
        # AuthServiceを使用
        result = await auth_service.authenticate_user(user_data.email, user_data.password)
        
        if result["success"]:
            # セッションを作成
            session_id = await auth_service.create_session(result["user"]["user_id"])
            
            if not session_id:
                raise HTTPException(status_code=500, detail="セッション作成に失敗しました")
            
            # HttpOnly CookieにセッションIDを設定
            response.set_cookie(
                key="session_id",
                value=session_id,
                httponly=True,
                max_age=30 * 60,  # 30分
                samesite="lax",
                secure=False  # 開発環境ではFalse、本番環境ではTrue
            )
            
            return AuthResponse(
                message=result["message"],
                user=UserResponse(
                    user_id=result["user"]["user_id"],
                    email=result["user"]["email"],
                    created_at=result["user"]["created_at"]
                )
            )
        else:
            raise HTTPException(status_code=401, detail=result["message"])
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="ログイン処理でエラーが発生しました")

@app.post("/api/logout")
async def logout(response: Response, session_id: Optional[str] = Cookie(None)):
    """ログアウト"""
    if session_id:
        await auth_service.invalidate_session(session_id)
    
    response.delete_cookie(key="session_id")
    return {"message": "ログアウトしました"}

@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user_id: int = Depends(get_current_user)):
    """現在のユーザー情報を取得"""
    user = await auth_service.get_user_by_id(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    
    return UserResponse(
        user_id=user["user_id"],
        email=user["email"],
        created_at=user["created_at"],
        last_login=user["last_login"]
    )