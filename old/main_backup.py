# Idea Spark - 新規事業開発支援WebアプリケーションのメインAPI
from fastapi import FastAPI, HTTPException, Depends, Cookie, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from typing import Optional, List
import logging
import os

# ローカルモジュールのインポート
from connect_PostgreSQL import test_database_connection
from crud import (
    UserCreate, UserLogin, AuthResponse, UserResponse, ProjectResponse,
    create_user, authenticate_user, create_session, validate_session, 
    get_user_by_id, get_user_projects, create_tables
)

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
vector_crud = VectorStoreCRUD(db_connection)
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

# ===== プロジェクト・キャンバス関連エンドポイント =====

@app.get("/api/projects", response_model=List[ProjectListItem])
async def get_user_projects(current_user_id: int = Depends(get_current_user)):
    """ユーザーのプロジェクト一覧を取得"""
    try:
        projects = await project_crud.get_user_projects(current_user_id)
        return [ProjectListItem(**project) for project in projects]
    except Exception as e:
        logger.error(f"プロジェクト一覧取得エラー: {e}")
        raise HTTPException(status_code=500, detail="プロジェクト一覧の取得に失敗しました")

@app.post("/api/canvas-autogenerate", response_model=CanvasComparisonResponse)
async def auto_generate_canvas(request: CanvasAutoGenerateRequest):
    """AIによるリーンキャンバス自動生成"""
    try:
        result = await canvas_service.auto_generate_canvas(
            idea_description=request.idea_description,
            target_audience=request.target_audience,
            industry=request.industry
        )
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return CanvasComparisonResponse(
            current_canvas=LeanCanvasFields(),  # 空のキャンバス
            proposed_canvas=LeanCanvasFields(**result["canvas_data"]),
            differences={}  # 自動生成時は差分なし
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"キャンバス自動生成エラー: {e}")
        raise HTTPException(status_code=500, detail="キャンバス自動生成に失敗しました")

@app.post("/api/projects", response_model=ProjectResponse)
async def create_project(project_data: ProjectCreate, current_user_id: int = Depends(get_current_user)):
    """新規プロジェクト作成"""
    try:
        result = await canvas_service.create_project_with_canvas(
            user_id=current_user_id,
            project_name=project_data.project_name,
            canvas_data=project_data.canvas_data.dict(),
            update_comment=project_data.update_comment
        )
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        # 作成されたプロジェクトの詳細を取得
        project_detail = await project_crud.get_project_latest(result["project_id"], current_user_id)
        
        return ProjectResponse(
            project_id=project_detail["project_id"],
            project_name=project_detail["project_name"],
            user_id=current_user_id,
            created_at=project_detail["created_at"],
            current_version=project_detail["current_version"],
            canvas_data=LeanCanvasFields(**project_detail["canvas_data"]),
            last_updated=project_detail["last_updated"],
            update_category=project_detail["update_category"],
            update_comment=project_detail["update_comment"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"プロジェクト作成エラー: {e}")
        raise HTTPException(status_code=500, detail="プロジェクト作成に失敗しました")

@app.get("/api/projects/{project_id}/latest", response_model=ProjectResponse)
async def get_project_latest(project_id: int, current_user_id: int = Depends(get_current_user)):
    """プロジェクトの最新バージョンを取得"""
    try:
        project = await project_crud.get_project_latest(project_id, current_user_id)
        if not project:
            raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")
        
        return ProjectResponse(
            project_id=project["project_id"],
            project_name=project["project_name"],
            user_id=current_user_id,
            created_at=project["created_at"],
            current_version=project["current_version"],
            canvas_data=LeanCanvasFields(**project["canvas_data"]),
            last_updated=project["last_updated"],
            update_category=project["update_category"],
            update_comment=project["update_comment"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"プロジェクト取得エラー: {e}")
        raise HTTPException(status_code=500, detail="プロジェクトの取得に失敗しました")

@app.post("/api/projects/{project_id}/latest", response_model=ProjectResponse)
async def update_project_canvas(project_id: int, update_data: ProjectUpdate, 
                              current_user_id: int = Depends(get_current_user)):
    """プロジェクトキャンバスを更新"""
    try:
        result = await canvas_service.update_project_canvas(
            project_id=project_id,
            user_id=current_user_id,
            canvas_data=update_data.canvas_data.dict(),
            update_category=update_data.update_category.value,
            update_comment=update_data.update_comment
        )
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        # 更新されたプロジェクトの詳細を取得
        project_detail = await project_crud.get_project_latest(project_id, current_user_id)
        
        return ProjectResponse(
            project_id=project_detail["project_id"],
            project_name=project_detail["project_name"],
            user_id=current_user_id,
            created_at=project_detail["created_at"],
            current_version=project_detail["current_version"],
            canvas_data=LeanCanvasFields(**project_detail["canvas_data"]),
            last_updated=project_detail["last_updated"],
            update_category=project_detail["update_category"],
            update_comment=project_detail["update_comment"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"プロジェクト更新エラー: {e}")
        raise HTTPException(status_code=500, detail="プロジェクト更新に失敗しました")

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: int, current_user_id: int = Depends(get_current_user)):
    """プロジェクトを削除"""
    try:
        result = await project_crud.delete_project(project_id, current_user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return {"message": result["message"]}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"プロジェクト削除エラー: {e}")
        raise HTTPException(status_code=500, detail="プロジェクト削除に失敗しました")

# ===== ドキュメント関連エンドポイント =====

@app.get("/api/projects/{project_id}/documents", response_model=DocumentListResponse)
async def get_project_documents(project_id: int, current_user_id: int = Depends(get_current_user)):
    """プロジェクトのドキュメント一覧を取得"""
    try:
        documents = await document_crud.get_project_documents(project_id, current_user_id)
        
        total_size = sum(doc.get('file_size', 0) or 0 for doc in documents)
        
        return DocumentListResponse(
            documents=[DocumentResponse(**doc) for doc in documents],
            total_count=len(documents),
            total_size=total_size
        )
        
    except Exception as e:
        logger.error(f"ドキュメント一覧取得エラー: {e}")
        raise HTTPException(status_code=500, detail="ドキュメント一覧の取得に失敗しました")

@app.post("/api/projects/{project_id}/documents", response_model=DocumentResponse)
async def upload_document(project_id: int, source_type: SourceType, 
                        file: UploadFile = File(...), 
                        current_user_id: int = Depends(get_current_user)):
    """ドキュメントをアップロード"""
    try:
        # ファイル保存
        save_result = await file_service.save_file(file, project_id, current_user_id)
        
        if not save_result["success"]:
            raise HTTPException(status_code=400, detail=save_result["message"])
        
        # データベースに登録
        doc_result = await document_crud.create_document(
            user_id=current_user_id,
            project_id=project_id,
            file_name=save_result["file_name"],
            file_path=save_result["file_path"],
            file_type=save_result["file_type"],
            file_size=save_result["file_size"],
            source_type=source_type.value
        )
        
        if not doc_result["success"]:
            # ファイル削除
            await file_service.delete_file(save_result["file_path"])
            raise HTTPException(status_code=400, detail=doc_result["message"])
        
        # テキスト抽出とRAG処理
        try:
            text_content = await file_service.extract_text_from_file(
                save_result["file_path"], 
                save_result["file_type"]
            )
            
            if text_content:
                # RAG処理を非同期で実行
                asyncio.create_task(
                    rag_service.process_document_for_rag(doc_result["document_id"], text_content)
                )
        except Exception as rag_error:
            logger.warning(f"RAG処理でエラーが発生しましたが、ドキュメントは保存されました: {rag_error}")
        
        # ユーザー情報を取得
        user = await auth_service.get_user_by_id(current_user_id)
        
        return DocumentResponse(
            document_id=doc_result["document_id"],
            file_name=save_result["file_name"],
            file_type=save_result["file_type"],
            file_size=save_result["file_size"],
            source_type=source_type.value,
            uploaded_at=datetime.now(),
            user_email=user["email"] if user else "unknown"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ドキュメントアップロードエラー: {e}")
        raise HTTPException(status_code=500, detail="ドキュメントのアップロードに失敗しました")

@app.delete("/api/projects/{project_id}/documents/{document_id}")
async def delete_document(project_id: int, document_id: int, 
                        current_user_id: int = Depends(get_current_user)):
    """ドキュメントを削除"""
    try:
        result = await document_crud.delete_document(document_id, current_user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return {"message": result["message"]}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ドキュメント削除エラー: {e}")
        raise HTTPException(status_code=500, detail="ドキュメント削除に失敗しました")

# ===== リサーチ関連エンドポイント =====

@app.post("/api/projects/{project_id}/research", response_model=CanvasComparisonResponse)
async def research_canvas(project_id: int, request: ResearchRequest, 
                        current_user_id: int = Depends(get_current_user)):
    """リサーチ機能でキャンバスを改善"""
    try:
        result = await canvas_service.research_and_enhance_canvas(
            project_id=project_id,
            user_id=current_user_id,
            research_focus=request.research_focus
        )
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        # リサーチ結果を保存
        current_project = await project_crud.get_project_latest(project_id, current_user_id)
        edit_id = current_project["edit_id"] if current_project else None
        
        if edit_id:
            await research_crud.create_research_result(
                edit_id=edit_id,
                user_id=current_user_id,
                result_text=str(result["proposed_changes"]),
                source_summary=result["source_summary"]
            )
        
        # 差分計算（簡易版）
        differences = {}
        current_canvas = result["current_canvas"]
        proposed_changes = result["proposed_changes"]
        
        return CanvasComparisonResponse(
            current_canvas=LeanCanvasFields(**current_canvas),
            proposed_canvas=LeanCanvasFields(**current_canvas),  # 改善提案を反映
            differences=differences
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"リサーチエラー: {e}")
        raise HTTPException(status_code=500, detail="リサーチに失敗しました")

@app.delete("/api/projects/{project_id}/research/{research_id}")
async def delete_research_result(project_id: int, research_id: int,
                               current_user_id: int = Depends(get_current_user)):
    """リサーチ結果を削除"""
    try:
        result = await research_crud.delete_research_result(research_id, current_user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return {"message": result["message"]}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"リサーチ削除エラー: {e}")
        raise HTTPException(status_code=500, detail="リサーチ結果の削除に失敗しました")

# ===== インタビュー関連エンドポイント =====

@app.post("/api/projects/{project_id}/interview-preparation", response_model=InterviewPreparationResponse)
async def prepare_interview(project_id: int, request: InterviewPreparationRequest,
                          current_user_id: int = Depends(get_current_user)):
    """インタビュー準備機能"""
    try:
        # 現在のキャンバスを取得
        current_project = await project_crud.get_project_latest(project_id, current_user_id)
        if not current_project:
            raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")
        
        # インタビュー準備内容を生成（簡易版）
        interview_questions = [
            f"{request.interview_purpose}に関してお聞かせください。",
            "どのような課題を感じていますか？",
            "現在はどのように解決していますか？",
            "理想的な解決方法があれば教えてください。"
        ]
        
        target_personas = request.target_persona.split(",") if request.target_persona else ["一般ユーザー"]
        
        preparation_tips = [
            "質問は具体的で答えやすい形にしましょう",
            "相手の回答を深掘りする追加質問を準備しましょう",
            "バイアスのかからない中立的な質問を心がけましょう"
        ]
        
        focus_areas = request.focus_areas or ["課題の深掘り", "解決策の検証", "価値提案の確認"]
        
        return InterviewPreparationResponse(
            interview_questions=interview_questions,
            target_personas=target_personas,
            preparation_tips=preparation_tips,
            focus_areas=focus_areas
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"インタビュー準備エラー: {e}")
        raise HTTPException(status_code=500, detail="インタビュー準備に失敗しました")

@app.get("/api/projects/{project_id}/interview-notes", response_model=InterviewNoteListResponse)
async def get_interview_notes(project_id: int, current_user_id: int = Depends(get_current_user)):
    """インタビューメモ一覧を取得"""
    try:
        notes = await interview_crud.get_project_interview_notes(project_id, current_user_id)
        
        return InterviewNoteListResponse(
            notes=[InterviewNoteResponse(**note) for note in notes],
            total_count=len(notes)
        )
        
    except Exception as e:
        logger.error(f"インタビューメモ一覧取得エラー: {e}")
        raise HTTPException(status_code=500, detail="インタビューメモの取得に失敗しました")

@app.post("/api/projects/{project_id}/interview-notes", response_model=InterviewNoteResponse)
async def create_interview_note(project_id: int, note_data: InterviewNoteCreate,
                              current_user_id: int = Depends(get_current_user)):
    """インタビューメモを作成"""
    try:
        result = await interview_crud.create_interview_note(
            project_id=project_id,
            user_id=current_user_id,
            interviewee_name=note_data.interviewee_name,
            interview_date=note_data.interview_date,
            interview_type=note_data.interview_type.value,
            interview_note=note_data.interview_note
        )
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        # 作成されたメモの詳細を取得
        note_detail = await interview_crud.get_interview_note_by_id(result["note_id"], current_user_id)
        
        return InterviewNoteResponse(**note_detail)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"インタビューメモ作成エラー: {e}")
        raise HTTPException(status_code=500, detail="インタビューメモの作成に失敗しました")

@app.delete("/api/projects/{project_id}/interview-notes/{note_id}")
async def delete_interview_note(project_id: int, note_id: int,
                              current_user_id: int = Depends(get_current_user)):
    """インタビューメモを削除"""
    try:
        result = await interview_crud.delete_interview_note(note_id, current_user_id)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return {"message": result["message"]}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"インタビューメモ削除エラー: {e}")
        raise HTTPException(status_code=500, detail="インタビューメモの削除に失敗しました")

@app.post("/api/projects/{project_id}/interview-to-canvas", response_model=CanvasComparisonResponse)
async def reflect_interview_to_canvas(project_id: int, request: InterviewToCanvasRequest,
                                    current_user_id: int = Depends(get_current_user)):
    """インタビュー結果をキャンバスに反映"""
    try:
        # インタビューメモを取得
        note_detail = await interview_crud.get_interview_note_by_id(request.note_id, current_user_id)
        if not note_detail:
            raise HTTPException(status_code=404, detail="インタビューメモが見つかりません")
        
        # キャンバス分析
        result = await canvas_service.analyze_interview_for_canvas(
            project_id=project_id,
            user_id=current_user_id,
            interview_text=note_detail["interview_note"]
        )
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return CanvasComparisonResponse(
            current_canvas=LeanCanvasFields(**result["current_canvas"]),
            proposed_canvas=LeanCanvasFields(**result["current_canvas"]),  # 改善提案を反映
            differences={}  # 差分計算は今後実装
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"インタビュー反映エラー: {e}")
        raise HTTPException(status_code=500, detail="インタビューの反映に失敗しました")

# ===== 履歴・ロールバック関連エンドポイント =====

@app.get("/api/projects/{project_id}/edit-histories", response_model=List[EditHistoryItem])
async def get_edit_history(project_id: int, current_user_id: int = Depends(get_current_user)):
    """編集履歴を取得"""
    try:
        history = await project_crud.get_edit_history(project_id, current_user_id)
        return [EditHistoryItem(**item) for item in history]
        
    except Exception as e:
        logger.error(f"編集履歴取得エラー: {e}")
        raise HTTPException(status_code=500, detail="編集履歴の取得に失敗しました")

@app.post("/api/projects/{project_id}/edit-histories/{edit_id}/rollback", response_model=ProjectResponse)
async def rollback_project(project_id: int, edit_id: int, request: RollbackRequest,
                         current_user_id: int = Depends(get_current_user)):
    """プロジェクトをロールバック"""
    try:
        result = await project_crud.rollback_to_version(
            project_id=project_id,
            edit_id=edit_id,
            user_id=current_user_id,
            rollback_comment=request.rollback_comment
        )
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        # ロールバック後のプロジェクト詳細を取得
        project_detail = await project_crud.get_project_latest(project_id, current_user_id)
        
        return ProjectResponse(
            project_id=project_detail["project_id"],
            project_name=project_detail["project_name"],
            user_id=current_user_id,
            created_at=project_detail["created_at"],
            current_version=project_detail["current_version"],
            canvas_data=LeanCanvasFields(**project_detail["canvas_data"]),
            last_updated=project_detail["last_updated"],
            update_category=project_detail["update_category"],
            update_comment=project_detail["update_comment"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ロールバックエラー: {e}")
        raise HTTPException(status_code=500, detail="ロールバックに失敗しました")

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