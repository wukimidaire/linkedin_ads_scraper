import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from fastapi import HTTPException

# Load environment variables
load_dotenv()

# Get individual database credentials
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("POSTGRES_HOST")
DB_PORT = os.getenv("POSTGRES_PORT")
DB_NAME = os.getenv("POSTGRES_DB")

# Base configuration
Base = declarative_base()

# Database URL and engine configuration
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_timeout=60,
    pool_pre_ping=True
)

# Session configuration
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_connection():
    try:
        with engine.connect() as conn:
            # Test basic connectivity
            conn.execute(text("SELECT 1"))
            
            # Check isolation level
            isolation = conn.execute(text("SHOW transaction_isolation")).scalar()
            autocommit = conn.execute(text("SHOW autocommit")).scalar()
            
            print(f"Database connected!")
            print(f"Isolation level: {isolation}")
            print(f"Autocommit: {autocommit}")
            return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False

async def health_check(db: Session):
    try:
        result = await db.execute(text("SELECT 1"))
        return {"status": "healthy", "message": "Database connection successful"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database health check failed: {str(e)}"
        )

async def test_db_connection(db: Session):
    try:
        result = db.execute(text("SELECT 1")).fetchone()
        return {"database": "connected", "test_query": result[0]}
    except Exception as e:
        return {"database": "error", "details": str(e)}
