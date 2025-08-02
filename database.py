# PostgreSQL + pgvector データベース接続設定
import os
import asyncpg
import psycopg2
from typing import Optional, Dict, Any
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)

class DatabaseConfig:
    """PostgreSQLデータベース設定クラス"""
    
    def __init__(self):
        # PostgreSQL接続設定
        self.host = os.getenv("DB_HOST", "localhost")
        self.port = int(os.getenv("DB_PORT", "5432"))
        self.user = os.getenv("DB_USER", "postgres")
        self.password = os.getenv("DB_PASSWORD", "password")
        self.database = os.getenv("DB_NAME", "idea_spark")
        
        # 接続文字列の作成
        self.sync_url = f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        self.async_url = f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        
        logger.info(f"Database config - Host: {self.host}, Port: {self.port}, Database: {self.database}")

class DatabaseConnection:
    """PostgreSQLデータベース接続クラス"""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._sync_engine = None
        self._async_engine = None
        self._session_factory = None
        self._connection_pool = None
    
    def get_sync_engine(self):
        """同期エンジンを取得"""
        if self._sync_engine is None:
            self._sync_engine = create_engine(
                self.config.sync_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                echo=False  # 本番では False
            )
        return self._sync_engine
    
    def get_async_engine(self):
        """非同期エンジンを取得"""
        if self._async_engine is None:
            self._async_engine = create_async_engine(
                self.config.async_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                echo=False  # 本番では False
            )
        return self._async_engine
    
    def get_session_factory(self):
        """セッションファクトリを取得"""
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.get_async_engine(),
                class_=AsyncSession,
                expire_on_commit=False
            )
        return self._session_factory
    
    async def get_async_connection(self) -> asyncpg.Connection:
        """非同期接続を取得（直接のasyncpg接続）"""
        try:
            connection = await asyncpg.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                command_timeout=60
            )
            return connection
        except Exception as e:
            logger.error(f"PostgreSQL接続エラー: {e}")
            raise
    
    def get_sync_connection(self) -> psycopg2.extensions.connection:
        """同期接続を取得（psycopg2）"""
        try:
            connection = psycopg2.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                connect_timeout=10
            )
            connection.autocommit = True
            return connection
        except Exception as e:
            logger.error(f"PostgreSQL同期接続エラー: {e}")
            raise
    
    async def test_connection(self) -> Dict[str, Any]:
        """データベース接続テスト"""
        try:
            conn = await self.get_async_connection()
            
            # pgvector拡張の確認
            pgvector_result = await conn.fetchrow("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            
            # バージョン情報取得
            version_result = await conn.fetchrow("SELECT version()")
            
            await conn.close()
            
            return {
                "status": "connected",
                "pgvector_enabled": pgvector_result[0] if pgvector_result else False,
                "postgres_version": version_result[0] if version_result else "unknown"
            }
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }

# SQLAlchemy Base
Base = declarative_base()

# グローバル設定とコネクション
db_config = DatabaseConfig()
db_connection = DatabaseConnection(db_config)

# セッション管理用のヘルパー関数
@asynccontextmanager
async def get_db_session():
    """データベースセッションを取得するコンテキストマネージャー"""
    session_factory = db_connection.get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def get_db():
    """FastAPI依存性注入用のデータベースセッション"""
    async with get_db_session() as session:
        yield session

# 接続テスト関数
async def test_database_connection():
    """データベース接続をテストする関数"""
    result = await db_connection.test_connection()
    logger.info(f"Database connection test result: {result}")
    return result