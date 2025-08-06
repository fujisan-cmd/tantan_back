# PostgreSQL データベース接続設定
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import logging

logger = logging.getLogger(__name__)

# 環境変数の読み込み
load_dotenv()

# データベース設定
DB_USER = os.getenv('DB_USER')#, 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD')#, 'password')
DB_HOST = os.getenv('DB_HOST')#, 'localhost')
DB_PORT = os.getenv('DB_PORT')#, '5432')
DB_NAME = os.getenv('DB_NAME')#, 'idea_spark')

# PostgreSQL接続URL
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# SQLAlchemyエンジンの作成
engine = create_engine(
    DATABASE_URL,
    echo=True,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# セッションメーカーの作成
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ベースクラスの作成
# Base = declarative_base()

def get_db():
    """データベースセッションの取得"""
    session = SessionLocal()
    try:
        yield session
    except Exception as e:
        session.rollback()
        logger.error(f"データベースエラー: {e}")
        raise
    finally:
        session.close()

def test_database_connection():
    """データベース接続テスト"""
    try:
        session = SessionLocal()
        session.execute("SELECT 1")
        session.close()
        logger.info("データベース接続成功")
        return {"status": "healthy", "message": "データベース接続成功"}
    except Exception as e:
        logger.error(f"データベース接続エラー: {e}")
        return {"status": "unhealthy", "message": f"データベース接続エラー: {e}"}
