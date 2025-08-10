# Idea Spark - 新規事業開発支援WebアプリケーションのメインAPI
from fastapi import FastAPI, HTTPException, Depends, Cookie, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from typing import Optional, List
import logging
import os

# ローカルモジュールのインポート
from connect_PostgreSQL import test_database_connection
from db_operations import (
    UserCreate, UserLogin, AuthResponse, UserResponse, ProjectResponse, ProjectCreateRequest,
    create_user, authenticate_user, create_session, validate_session, 
    get_user_by_id, get_user_projects, create_tables, get_latest_edit_id,
    get_canvas_details,
    insert_project, insert_edit_history, insert_canvas_details,
)

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Idea Spark API",
    description="新規事業開発支援WebアプリケーションのAPI",
    version="1.0.0"
)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
logger.info(f"CORS allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 本番環境ではallowed_originsを使用すること
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 依存関数：現在のユーザーを取得
def get_current_user(session_id: str = Cookie(None)) -> int:
    """セッションからユーザーIDを取得"""
    if not session_id:
        raise HTTPException(status_code=401, detail="認証が必要です")
    
    user_id = validate_session(session_id)
    if not user_id:
        raise HTTPException(status_code=401, detail="無効なセッションです")
    
    return user_id

# === エンドポイント ===

@app.get("/")
def index():
    """ルートエンドポイント"""
    return {"message": "Hello Idea Spark API!"}

@app.get("/health")
def health_check():
    """ヘルスチェック"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}

@app.get("/health/detailed")
def detailed_health_check():
    """詳細ヘルスチェック"""
    db_status = test_database_connection()
    return {
        "status": "healthy" if db_status["status"] == "healthy" else "unhealthy",
        "timestamp": datetime.utcnow(),
        "database": db_status
    }

@app.post("/api/signup", response_model=AuthResponse)
def signup(user_data: UserCreate, response: Response, request: Request):
    """ユーザー登録"""
    # クライアントIP取得
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"Signup attempt from {client_ip} for email: {user_data.email}")
    
    # ユーザー作成
    result = create_user(user_data.email, user_data.password)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    # セッション作成
    session_id = create_session(result["user_id"])
    if not session_id:
        raise HTTPException(status_code=500, detail="セッション作成に失敗しました")
    
    # セッションCookie設定
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=False,  # HTTPS環境では True に設定
        samesite="lax",
        max_age=86400  # 24時間
    )
    
    # ユーザー情報取得
    user_info = get_user_by_id(result["user_id"])
    if user_info:
        user_response = UserResponse(**user_info)
    else:
        user_response = None
    
    return AuthResponse(
        message="ユーザー登録が完了しました",
        user=user_response
    )

@app.post("/api/login", response_model=AuthResponse)
def login(user_data: UserLogin, response: Response, request: Request):
    """ユーザーログイン"""
    # クライアントIP取得
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"Login attempt from {client_ip} for email: {user_data.email}")
    
    # ユーザー認証
    result = authenticate_user(user_data.email, user_data.password)
    
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["message"])
    
    # セッション作成
    session_id = create_session(result["user_id"])
    if not session_id:
        raise HTTPException(status_code=500, detail="セッション作成に失敗しました")
    
    # セッションCookie設定
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=False,  # HTTPS環境では True に設定
        samesite="lax",
        max_age=86400  # 24時間
    )
    
    # ユーザー情報取得
    user_info = get_user_by_id(result["user_id"])
    if user_info:
        user_response = UserResponse(**user_info)
    else:
        user_response = None
    
    return AuthResponse(
        message="ログインしました",
        user=user_response
    )

@app.post("/api/logout")
def logout(response: Response):
    """ログアウト"""
    # セッションCookie削除
    response.delete_cookie("session_id")
    return {"message": "ログアウトしました"}

@app.get("/api/auth/me", response_model=UserResponse)
def get_current_user_info(current_user_id: int = Depends(get_current_user)):
    """現在のユーザー情報取得"""
    user_info = get_user_by_id(current_user_id)
    if not user_info:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    
    return UserResponse(**user_info)

@app.get("/api/projects", response_model=List[ProjectResponse])
def get_projects(current_user_id: int = Depends(get_current_user)):
    """ユーザーのプロジェクト一覧取得"""
    projects = get_user_projects(current_user_id)
    return [ProjectResponse(**project) for project in projects]

@app.get("/projects/{project_id}/latest")
def get_latest_canvas(project_id: int):
    # response_modelと認証機能は後で実装する
    edit_id = get_latest_edit_id(project_id)
    print(f"最新の編集ID: {edit_id}")
    details = get_canvas_details(edit_id)
    return details

@app.post("/projects")
def register_project(request: ProjectCreateRequest):
    # 'created_at'はDB側で自動設定するため、ここでは指定しない
    value = {
        'user_id': request.user_id,
        'project_name': request.project_name,
    }
    project_id = insert_project(value)
    print(f"新規プロジェクト登録: {project_id}")
    # edit_historyテーブルにデータを挿入、versionは1に設定、edit_idを返却
    edit_id = insert_edit_history(project_id, version=1, user_id=request.user_id, update_category="manual")
    print(f"プロジェクトの編集履歴登録: {edit_id}")
    # edit_idを使ってdetailテーブルにデータを挿入
    result = insert_canvas_details(edit_id, request.field)
    return {"project_id": project_id, "edit_id": edit_id, "result": result}

# アプリケーション起動時にテーブル作成
@app.on_event("startup")
def startup_event():
    """アプリケーション起動時の処理"""
    logger.info("アプリケーションを起動しています...")
    create_tables()
    logger.info("アプリケーションの起動が完了しました")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)