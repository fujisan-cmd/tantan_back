# Idea Spark - 新規事業開発支援WebアプリケーションのメインAPI
from fastapi import FastAPI, HTTPException, Depends, Cookie, Response, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from typing import Optional, List
import logging
import os
from dotenv import load_dotenv
from openai import OpenAI
import json

load_dotenv()
api_key = os.getenv("API_KEY")
client = OpenAI(api_key=api_key)

# ローカルモジュールのインポート
from connect_PostgreSQL import test_database_connection
from db_operations import (
    UserCreate, UserLogin, AuthResponse, UserResponse, ProjectResponse, ProjectCreateRequest, ProjectWithAI, ProjectUpdateRequest, InterviewNotesRequest,
    create_user, authenticate_user, create_session, validate_session, 
    get_user_by_id, get_user_projects, create_tables, get_latest_edit_id, get_project_documents,
    get_canvas_details, get_latest_version, get_project_by_id,
    insert_project, insert_edit_history, insert_canvas_details, 
    insert_research_result, remove_research_result, insert_interview_notes, get_all_interview_notes, delete_one_note, 
    delete_documents_record, get_document_by_id,
    # RAG機能用追加
    DocumentUploadResponse, TextDocumentResponse, SearchRequest, SearchResult, CanvasGenerationRequest,
    create_document_record,  # 追加
    # 整合性確認機能用追加
    ConsistencyCheckRequest, ConsistencyCheckResponse,
    # AI回答自動生成機能用追加
    AutoAnswerGenerationRequest, AutoAnswerGenerationResponse,
    # リーンキャンバス更新案生成機能用追加
    CanvasUpdateRequest, CanvasUpdateResponse,
    InterviewToCanvasRequest, InterviewToCanvasResponse, get_interview_note_by_id, get_project_history_list, get_edit_id_by_version
)

# RAG機能用サービス
from services.file_service import FileService
from services.rag_service import RAGService
# 整合性確認機能用サービス
from services.consistency_service import ConsistencyService
# AI回答自動生成機能用サービス
from services.auto_answer_service import AutoAnswerService
# リーンキャンバス更新案生成機能用サービス
from services.canvas_update_service import CanvasUpdateService

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

# RAG機能用サービスインスタンス
file_service = FileService()
rag_service = RAGService()
# 整合性確認機能用サービスインスタンス
consistency_service = ConsistencyService()
# AI回答自動生成機能用サービスインスタンス
auto_answer_service = AutoAnswerService()
# リーンキャンバス更新案生成機能用サービスインスタンス
canvas_update_service = CanvasUpdateService()

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

@app.get("/api/users/{user_id}")
def get_user_email(user_id: int):
    """ユーザーIDからemailを取得"""
    user_info = get_user_by_id(user_id)
    if not user_info:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    return {"user_id": user_info["user_id"], "email": user_info["email"]}

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
    edit_id = insert_edit_history(project_id, version=1, user_id=request.user_id, update_category="manual", update_comment="初回登録")
    print(f"プロジェクトの編集履歴登録: {edit_id}")
    # edit_idを使ってdetailテーブルにデータを挿入
    result = insert_canvas_details(edit_id, request.field)
    return {"project_id": project_id, "edit_id": edit_id, "result": result}

@app.post("/canvas-autogenerate")
def auto_generate_canvas(request: ProjectWithAI):
    request = '今から新規事業開発のリーンキャンバスを作成します。' \
            'アイデアの概要を以下に提示しますので、リーンキャンバスの各項目を日本語で作成してください。'\
            '解答には余計な文章を挿入せず、必ず以下の書式を埋める形で回答してください。idea_nameなどのkeyは日本語にせずそのまま返してください：{"idea_name": "", "Problem": "","Customer_Segments": "","Unique_Value_Proposition": "","Solution": "","Channels": "","Revenue_Streams": "","Cost_Structure": "","Key_Metrics": "","Unfair_Advantage": "","Early_Adopters": "","Existing_Alternatives": ""} ## アイデア概要' \
            + request.idea_draft
    response = client.chat.completions.create(
        model='gpt-4o', 
        messages=[
            {'role': 'user', "content": request},
        ],
    )
    output_content = response.choices[0].message.content.strip()
    result = json.loads(output_content)
    return result

@app.post("/projects/{project_id}/latest")
def update_canvas(request: ProjectUpdateRequest):
    try:
        version = get_latest_version(request.project_id)
        if version is None:
            version = 0  # 初回の場合は0から開始
        print(f"最新の編集バージョン: {version}")
        
        # update_categoryをリクエストから渡す
        edit_id = insert_edit_history(request.project_id, version + 1, user_id=request.user_id, update_category=request.update_category, update_comment=request.update_comment)
        print(f"プロジェクトの編集履歴登録: {edit_id}")
        
        if edit_id == 0:
            raise HTTPException(status_code=500, detail="編集履歴の登録に失敗しました")
        
        success = insert_canvas_details(edit_id, request.field)
        if not success:
            raise HTTPException(status_code=500, detail="キャンバス詳細の登録に失敗しました")
        
        return {"success": True, "message": "キャンバスが正常に更新されました"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"キャンバス更新エラー: {e}")
        raise HTTPException(status_code=500, detail=f"キャンバス更新中にエラーが発生しました: {str(e)}")

@app.post("/projects/{project_id}/research")
def execute_research(project_id: int, current_user_id: int = Depends(get_current_user)):
    edit_id = get_latest_edit_id(project_id)
    details = get_canvas_details(edit_id)
    current_canvas = next(iter(details.values())) # detailsは2重の辞書になっているので、内側だけを取得

    # 本当はここの検索対象にRAGが追加される
    request1 = '現在リーンキャンバスをもとに新規事業開発を検討しています。以下に開発内容の概要を提示しますので、' \
            '以下の調査項目欄に指定した観点で調査を行ってください。' \
            '## 調査項目 - 3C分析(市場の成長性・競合他社状況・顧客のニーズ) - 技術調査(必要な技術・実現可能性) - 法規制調査 ' \
            '調査結果は簡潔に箇条書きでまとめ、余計な文章を挿入せずに、必ず以下の書式欄を埋める形で回答してください。' \
            '【市場調査結果】1. 市場の成長性 2. 競合分析 3. 顧客ニーズ調査【技術調査結果】1. 必要な技術と要求仕様 2. 実現可能性【法規制事項】1. 規制' \
            '## アイデア概要 '+str(current_canvas)
    response1 = client.chat.completions.create(
        model='gpt-4o', 
        messages=[
            {'role': 'user', "content": request1},
        ],
    )
    output_content1 = response1.choices[0].message.content.strip() # 調査結果のテキスト
    
    request2 = '現在リーンキャンバスをもとに新規事業開発を検討しています。以下に開発内容の概要は以下の通りです。' \
            + str(current_canvas) + \
            'また、このリーンキャンバスをもとに外部環境調査などを行った結果が以下の通りです。' \
            + output_content1 + \
            '両者を比較したうえで、リーンキャンバスを更新した方が良い項目とその具体的な更新例を3つ提案してください。' \
            'その際、必ず 項目1: 更新例1, 項目2: 更新例2, 項目3: 更新例3 のように、JSON形式で回答してください。' \
            'なお、更新例はなるべく元のリーンキャンバスの文体に合わせてください。'
    response2 = client.chat.completions.create(
        model='gpt-4o', 
        messages=[
            {'role': 'user', "content": request2},
        ],
    )
    output_content2 = response2.choices[0].message.content.strip() # 更新提案のテキスト
    print(f"更新提案: {output_content2}")

    is_success = insert_research_result(edit_id, current_user_id, output_content1)
    return {"success": is_success, "research_result": output_content1, "update_proposal": output_content2}

@app.delete("/projects/{project_id}/research/{research_id}")
def delete_one_research(project_id: int, research_id: int):
    result = remove_research_result(research_id)
    if not result:
        raise HTTPException(status_code=500, detail="リサーチ結果の削除に失敗しました")
    return {"success": True, "message": "リサーチ結果が正常に削除されました"}

@app.post("/projects/{project_id}/interview-preparation")
def interview_preparation(project_id: int, sel: str):
    edit_id = get_latest_edit_id(project_id)
    details = get_canvas_details(edit_id)
    current_canvas = next(iter(details.values())) # detailsは2重の辞書になっているので、内側だけを取得

    if sel == 'CPF':
        purpose = 'CustomerとProblemの整合性、すなわち想定している顧客が本当にその課題を持っているか、その課題が本当に痛みを伴うものか'
    elif sel == 'PSF':
        purpose = 'ProblemとSolutionの整合性、すなわち提案するソリューションが本当にその課題を解決できるか、顧客がそのソリューションを求めるか'

    request1 = '現在リーンキャンバスをもとに新規事業開発を検討しています。' \
            '開発の概要は以下の通りです。' + str(current_canvas) + \
            'ここで、' + purpose + 'を確認するためのインタビューを行いたいと考えています。' \
            '理想的なインタビュー対象者を、余計な文章を挿入せずに、必ず ' \
            '属性: [属性の箇条書きリスト], 特徴: [特徴の箇条書きリスト], 選定基準: [選定基準の箇条書きリスト] のように、JSON形式で回答してください。'
    response1 = client.chat.completions.create(
        model='gpt-4o', 
        messages=[
            {'role': 'user', "content": request1},
        ],
    )
    output_content1 = response1.choices[0].message.content.strip() # インタビュイーのテキスト

    request2 = '現在リーンキャンバスをもとに新規事業開発を検討しています。' \
            '開発の概要は以下の通りです。' + str(current_canvas) + \
            'ここで、' + purpose + 'を確認するため、以下のような人物にインタビューを行いたいと考えています。' \
            + str(output_content1) + \
            'およそ1時間のインタビュー時間で、この人物に対して効果的に仮説検証を行うための質問案を、余計な文章を挿入せずに、必ず' \
            '顧客の基本情報: [基本情報に関する質問案の箇条書きリスト], 現在の課題と痛み: [現在の課題と痛みに関する質問案の箇条書きリスト], ' \
            '代替手段の利用状況: [代替手段の利用状況に関する質問案の箇条書きリスト], 価値観と意思決定要因: [価値観と意思決定要因に関する質問案の箇条書きリスト]' \
            'のように、JSON形式で回答してください。'
    response2 = client.chat.completions.create(
        model='gpt-4o', 
        messages=[
            {'role': 'user', "content": request2},
        ],
    )
    output_content2 = response2.choices[0].message.content.strip() # 質問案のテキスト

    return {"interviewee": output_content1, "questions": output_content2}

@app.post("/projects/{project_id}/interview-notes")
def save_interview_notes(request: InterviewNotesRequest):
    result = insert_interview_notes(request.edit_id, request.project_id, request.user_id, request.interviewee_name, request.interview_date, request.interview_type, request.interview_note)
    if not result:
        raise HTTPException(status_code=500, detail="インタビューメモの登録に失敗しました")
        
    return {"success": True, "message": "インタビューメモが正常に登録されました"}

@app.get("/projects/{project_id}/interview-notes")
def get_interview_notes(project_id: int):
    result = get_all_interview_notes(project_id)
    return result

@app.delete("/projects/{project_id}/interview-notes/{note_id}")
def delete_interview_note(project_id: int, note_id: int):
    """インタビューメモを削除"""
    note = get_interview_note_by_id(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="インタビューメモが見つかりません")
    
    if note["project_id"] != project_id:
        raise HTTPException(status_code=403, detail="このプロジェクトのインタビューメモではありません")
    
    success = delete_one_note(note_id)
    if not success:
        raise HTTPException(status_code=500, detail="インタビューメモの削除に失敗しました")
    
    return {"success": True, "message": "インタビューメモが正常に削除されました"}

# === RAG機能用エンドポイント ===

@app.post("/api/projects/{project_id}/upload-and-process")
async def upload_and_process_file(
    project_id: int,
    file: UploadFile = File(...),
    source_type: str = Form(...),
    current_user_id: int = Depends(get_current_user)
):
    """ファイルアップロード→テキスト抽出→RAG処理→元ファイル削除"""
    try:
        logger.info(f"ファイル処理開始: {file.filename}, プロジェクト: {project_id}")
        
        # 1. ファイル処理とテキスト抽出（一時ファイル使用）
        extraction_result = await file_service.process_uploaded_file_and_extract_text(file)
        
        if not extraction_result["success"]:
            raise HTTPException(status_code=400, detail=extraction_result["message"])
        
        # 2. ドキュメント記録をDBに作成
        document_id = create_document_record(
            user_id=current_user_id,
            project_id=project_id,
            file_name=extraction_result["file_info"]["original_filename"],
            file_type=extraction_result["file_info"]["file_type"],
            file_size=extraction_result["file_info"]["file_size"],
            source_type=source_type
        )
        
        if not document_id:
            raise HTTPException(status_code=500, detail="ドキュメント記録の作成に失敗しました")
        
        # 3. RAG処理（テキスト分割・ベクトル化・保存）
        rag_result = await rag_service.process_text_for_rag(
            document_id=document_id,
            text_content=extraction_result["extracted_text"]
        )
        
        if not rag_result["success"]:
            logger.error(f"RAG処理失敗: {rag_result.get('message', 'Unknown error')}")
            # ドキュメント記録は残す（失敗状態で）
        
        # 4. 処理状況更新
        # update_document_processing_status(document_id, 'completed' if rag_result["success"] else 'failed')
        
        # 処理完了レスポンス
        logger.info(f"ファイル処理完了: {file.filename}")
        return {
            "message": "ファイル処理とRAG処理が完了しました",
            "document_id": document_id,
            "file_info": extraction_result["file_info"],
            "text_length": len(extraction_result["extracted_text"]),
            "text_preview": extraction_result["extracted_text"][:200] + "...",
            "rag_processing": rag_result if 'rag_result' in locals() else {"success": False, "message": "RAG処理がスキップされました"}
        }
        
    except Exception as e:
        logger.error(f"ファイル処理エラー: {e}")
        raise HTTPException(status_code=500, detail=f"ファイル処理に失敗しました: {str(e)}")

# @app.get("/api/projects/{project_id}/documents")
# async def get_project_documents_list(
#     project_id: int,
#     current_user_id: int = Depends(get_current_user)
# ):
#     """プロジェクトのアップロード済み文書一覧取得"""
#     try:
#         # documents = get_project_documents(project_id, current_user_id)
#         # 一時的なレスポンス（データベーススキーマ適用前）
#         return {
#             "message": "文書一覧機能は準備中です",
#             "documents": []
#         }
        
#     except Exception as e:
#         logger.error(f"文書一覧取得エラー: {e}")
#         raise HTTPException(status_code=500, detail="文書一覧の取得に失敗しました")

@app.post("/api/projects/{project_id}/search")
async def search_relevant_content(
    project_id: int,
    search_request: SearchRequest,
    current_user_id: int = Depends(get_current_user)
):
    """ベクトル検索でプロジェクト内の関連コンテンツを検索"""
    try:
        logger.info(f"ベクトル検索開始: プロジェクト{project_id}, クエリ: {search_request.query}")
        
        # RAG検索実行
        search_results = await rag_service.search_relevant_content(
            query=search_request.query,
            project_id=project_id,
            limit=search_request.limit
        )
        
        return {
            "query": search_request.query,
            "results_count": len(search_results),
            "results": search_results
        }
        
    except Exception as e:
        logger.error(f"ベクトル検索エラー: {e}")
        raise HTTPException(status_code=500, detail="検索に失敗しました")

@app.post("/api/canvas-generate-from-text")
async def generate_canvas_from_idea(
    canvas_request: CanvasGenerationRequest,
    current_user_id: int = Depends(get_current_user)
):
    """アイデアテキストからリーンキャンバスを自動生成"""
    try:
        logger.info(f"キャンバス自動生成開始: {canvas_request.idea_description[:50]}...")
        
        # AIによるキャンバス生成
        generation_result = await rag_service.generate_canvas_from_idea(
            idea_description=canvas_request.idea_description,
            target_audience=canvas_request.target_audience,
            industry=canvas_request.industry
        )
        
        if not generation_result["success"]:
            raise HTTPException(status_code=500, detail=generation_result["message"])
        
        return {
            "message": generation_result["message"],
            "canvas_data": generation_result["canvas_data"],
            "generated_by": "AI (OpenAI GPT-4o)"
        }
        
    except Exception as e:
        logger.error(f"キャンバス自動生成エラー: {e}")
        raise HTTPException(status_code=500, detail="キャンバス生成に失敗しました")

@app.delete("/api/projects/{project_id}/documents/{document_id}")
async def delete_document(
    project_id: int,
    document_id: int,
    current_user_id: int = Depends(get_current_user)
):
    """文書を削除（ベクトルデータも含む）"""
    try:
        success = delete_document_record(document_id, current_user_id)
        
        if success:
            return {
                "message": "文書を削除しました",
                "document_id": document_id
            }
        else:
            raise HTTPException(status_code=404, detail="文書が見つかりません")
        
    except Exception as e:
        logger.error(f"文書削除エラー: {e}")
        raise HTTPException(status_code=500, detail="文書削除に失敗しました")


@app.post("/api/projects/{project_id}/consistency-check", response_model=ConsistencyCheckResponse)
async def check_canvas_consistency(
    project_id: int,
    current_user_id: int = Depends(get_current_user)
):
    """リーンキャンバス整合性確認"""
    try:
        # プロジェクトの存在確認とユーザー権限チェック
        project = get_project_by_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")
        
        if project["user_id"] != current_user_id:
            raise HTTPException(status_code=403, detail="他のユーザーのプロジェクトを確認することはできません")
        
        # 最新バージョンのキャンバスデータを取得
        latest_edit_id = get_latest_edit_id(project_id)
        if not latest_edit_id:
            raise HTTPException(status_code=404, detail="プロジェクトのキャンバスデータが見つかりません")
        
        latest_canvas_details = get_canvas_details(latest_edit_id)
        if not latest_canvas_details:
            raise HTTPException(status_code=404, detail="キャンバスの詳細データが見つかりません")
        
        # 最新のキャンバスデータを使用して整合性分析を実行
        analysis_result = await consistency_service.analyze_canvas_consistency({
            "project_name": project["project_name"],
            "field": latest_canvas_details
        })
        
        if not analysis_result["success"]:
            raise HTTPException(status_code=500, detail=analysis_result["message"])
        
        return ConsistencyCheckResponse(
            success=True,
            analysis=analysis_result["analysis"],
            analyzed_at=analysis_result["analyzed_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"整合性確認エラー: {e}")
        raise HTTPException(status_code=500, detail="整合性確認の処理に失敗しました")

@app.post("/api/projects/{project_id}/consistency-check/test", response_model=ConsistencyCheckResponse)
async def test_canvas_consistency_check(
    project_id: int
):
    """リーンキャンバス整合性確認（テスト用、認証不要）"""
    try:
        # プロジェクトの存在確認
        project = get_project_by_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")
        
        # 最新バージョンのキャンバスデータを取得
        latest_edit_id = get_latest_edit_id(project_id)
        if not latest_edit_id:
            raise HTTPException(status_code=404, detail="プロジェクトのキャンバスデータが見つかりません")
        
        latest_canvas_details = get_canvas_details(latest_edit_id)
        if not latest_canvas_details:
            raise HTTPException(status_code=404, detail="キャンバスの詳細データが見つかりません")
        
        # 最新のキャンバスデータを使用して整合性分析を実行
        analysis_result = await consistency_service.analyze_canvas_consistency({
            "project_name": project["project_name"],
            "field": latest_canvas_details
        })
        
        if not analysis_result["success"]:
            raise HTTPException(status_code=500, detail=analysis_result["message"])
        
        return ConsistencyCheckResponse(
            success=True,
            analysis=analysis_result["analysis"],
            analyzed_at=analysis_result["analyzed_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"整合性確認テストエラー: {e}")
        raise HTTPException(status_code=500, detail="整合性確認の処理に失敗しました")

@app.post("/api/projects/{project_id}/auto-answer", response_model=AutoAnswerGenerationResponse)
async def generate_auto_answers(
    project_id: int,
    request: AutoAnswerGenerationRequest,
    current_user_id: int = Depends(get_current_user)
):
    """AI回答自動生成"""
    try:
        # プロジェクトの存在確認とユーザー権限チェック
        project = get_project_by_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")
        
        if project["user_id"] != current_user_id:
            raise HTTPException(status_code=403, detail="他のユーザーのプロジェクトで回答を生成することはできません")
        
        # 最新バージョンのキャンバスデータを取得
        latest_edit_id = get_latest_edit_id(project_id)
        if not latest_edit_id:
            raise HTTPException(status_code=404, detail="プロジェクトのキャンバスデータが見つかりません")
        
        latest_canvas_details = get_canvas_details(latest_edit_id)
        if not latest_canvas_details:
            raise HTTPException(status_code=404, detail="キャンバスの詳細データが見つかりません")
        
        # AI回答生成を実行
        result = await auto_answer_service.generate_answers(
            project_name=project["project_name"],
            questions=request.questions,
            canvas_data=latest_canvas_details
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        
        return AutoAnswerGenerationResponse(
            success=True,
            answers=result["answers"],
            generated_at=result["generated_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI回答生成エラー: {e}")
        raise HTTPException(status_code=500, detail="AI回答生成の処理に失敗しました")

@app.post("/api/projects/{project_id}/canvas-update", response_model=CanvasUpdateResponse)
async def generate_canvas_update(
    project_id: int,
    request: CanvasUpdateRequest,
    current_user_id: int = Depends(get_current_user)
):
    """リーンキャンバス更新案生成"""
    try:
        # プロジェクトの存在確認とユーザー権限チェック
        project = get_project_by_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")
        
        if project["user_id"] != current_user_id:
            raise HTTPException(status_code=403, detail="他のユーザーのプロジェクトで更新案を生成することはできません")
        
        # 最新バージョンのキャンバスデータを取得
        latest_edit_id = get_latest_edit_id(project_id)
        if not latest_edit_id:
            raise HTTPException(status_code=404, detail="プロジェクトのキャンバスデータが見つかりません")
        
        latest_canvas_details = get_canvas_details(latest_edit_id)
        if not latest_canvas_details:
            raise HTTPException(status_code=404, detail="キャンバスの詳細データが見つかりません")
        
        # リーンキャンバス更新案生成を実行
        result = await canvas_update_service.generate_canvas_update(
            project_name=project["project_name"],
            canvas_data=latest_canvas_details,
            user_answers=request.user_answers
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        
        return CanvasUpdateResponse(
            success=True,
            updated_canvas=result["updated_canvas"],
            generated_at=result["generated_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"リーンキャンバス更新案生成エラー: {e}")
        raise HTTPException(status_code=500, detail="リーンキャンバス更新案生成の処理に失敗しました")

@app.post("/projects/{project_id}/interview-to-canvas", response_model=InterviewToCanvasResponse)
async def interview_to_canvas(
    project_id: int,
    request: InterviewToCanvasRequest,
    current_user_id: int = Depends(get_current_user)
):
    """
    インタビューメモをもとに現行キャンバス＋提案キャンバスを返す（差分は返さない）
    """
    try:
        # プロジェクト存在・権限チェック
        project = get_project_by_id(project_id)
        if not project:
            return InterviewToCanvasResponse(success=False, message="プロジェクトが見つかりません")
        if project["user_id"] != current_user_id:
            return InterviewToCanvasResponse(success=False, message="他のユーザーのプロジェクトです")

        # インタビューメモ取得
        note = get_interview_note_by_id(request.note_id)
        if not note:
            return InterviewToCanvasResponse(success=False, message="インタビューメモが見つかりません")

        # 現行キャンバス取得
        latest_edit_id = get_latest_edit_id(project_id)
        if not latest_edit_id:
            return InterviewToCanvasResponse(success=False, message="現行キャンバスが見つかりません")
        latest_canvas_details = get_canvas_details(latest_edit_id)
        if not latest_canvas_details:
            return InterviewToCanvasResponse(success=False, message="キャンバス詳細が見つかりません")

        # LLM呼び出し用にuser_answers形式へ変換（仮: interview_noteを1件だけ渡す）
        user_answers = [
            {
                "question": f"インタビューメモ: {note['interviewee_name']} ({note['interview_date']})",
                "answer": note["interview_note"],
                "perspective": str(note["interview_type"])
            }
        ]
        result = await canvas_update_service.generate_canvas_update(
            project_name=project["project_name"],
            canvas_data=latest_canvas_details,
            user_answers=user_answers
        )
        if not result["success"]:
            return InterviewToCanvasResponse(success=False, message=result.get("message", "LLM生成に失敗"))

        # 現行キャンバスのfield部分を抽出
        current_canvas = next(iter(latest_canvas_details.values())) if isinstance(latest_canvas_details, dict) else latest_canvas_details
        proposed_canvas = result["updated_canvas"]

        return InterviewToCanvasResponse(
            success=True,
            current_canvas=current_canvas,
            proposed_canvas=proposed_canvas,
            message="提案キャンバスを生成しました"
        )
    except Exception as e:
        logger.error(f"interview-to-canvasエラー: {e}")
        return InterviewToCanvasResponse(success=False, message=f"サーバーエラー: {str(e)}")

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

#アップロード文書表示機能
@app.get("/projects/{project_id}/documents")
def get_documents(project_id: int, current_user_id: int = Depends(get_current_user)):
    try:
        documents = get_project_documents(project_id)
        print(f"プロジェクト{project_id}の文書一覧: {len(documents)}件")
        return documents
    except Exception as e:
        logger.error(f"文書一覧取得エラー: {e}")
        raise HTTPException(status_code=500, detail="文書一覧の取得に失敗しました")

@app.get("/projects/{project_id}/history-list")
def get_project_history_list_endpoint(project_id: int):
    """指定プロジェクトの編集履歴リストを返す"""
    try:
        history_list = get_project_history_list(project_id)
        return history_list
    except Exception as e:
        logger.error(f"編集履歴リスト取得エラー: {e}")
        raise HTTPException(status_code=500, detail="編集履歴リストの取得に失敗しました")

@app.get("/projects/{project_id}/{version}")
def get_canvas_by_version(project_id: int, version: int):
    """指定したバージョンのリーンキャンバス内容を返す"""
    edit_id = get_edit_id_by_version(project_id, version)
    if not edit_id:
        raise HTTPException(status_code=404, detail="指定バージョンのキャンバスが見つかりません")
    details = get_canvas_details(edit_id)
    return details
#文書削除機能
# main.py の文書削除エンドポイント（インタビューメモ削除と同じパターン）

@app.delete("/projects/{project_id}/documents/{document_id}")
def delete_document_endpoint(
    project_id: int,
    document_id: int,
    current_user_id: int = Depends(get_current_user)
):
    """文書を削除"""
    # 文書取得（権限チェック付き）
    document = get_document_by_id(document_id, current_user_id)
    if not document:
        raise HTTPException(status_code=404, detail="文書が見つからないか、削除権限がありません")
    
    # プロジェクトID整合性チェック
    if document["project_id"] != project_id:
        raise HTTPException(status_code=403, detail="このプロジェクトの文書ではありません")
    
    # 削除実行
    success = delete_documents_record(document_id, current_user_id)
    if not success:
        raise HTTPException(status_code=500, detail="文書の削除に失敗しました")
    
    return {
        "success": True, 
        "message": "文書が正常に削除されました",
        "document_id": document_id
    }

