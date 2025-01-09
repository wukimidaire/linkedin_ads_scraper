import os
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from typing import AsyncGenerator

# Load environment variables
load_dotenv()

# Get individual database credentials
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("POSTGRES_HOST")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB")
CLOUD_SQL_INSTANCE = os.getenv("CLOUD_SQL_INSTANCE")

# Base configuration
Base = declarative_base()

def get_database_url():
    """Get database URL with fallback to Cloud SQL instance"""
    try:
        if CLOUD_SQL_INSTANCE and "K_SERVICE" in os.environ:
            # Cloud SQL connection
            return f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@/{DB_NAME}?host=/cloudsql/{CLOUD_SQL_INSTANCE}"
        else:
            # Standard PostgreSQL connection
            return f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    except Exception as e:
        print(f"Failed to construct database URL: {e}")
        raise

# Database URL and engine configuration
try:
    DATABASE_URL = get_database_url()
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_pre_ping=True,
        pool_recycle=300
    )

    # Session configuration
    AsyncSessionLocal = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
except Exception as e:
    print(f"Failed to initialize database: {e}")
    raise

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Async database session dependency"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def test_connection():
    """Test async database connection"""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False

async def health_check(db: AsyncSession):
    """Async health check"""
    try:
        result = await db.execute(text("SELECT 1"))
        return {"status": "healthy", "message": "Database connection successful"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database health check failed: {str(e)}"
        )
