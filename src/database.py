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
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB")
CLOUD_SQL_INSTANCE = os.getenv("CLOUD_SQL_INSTANCE")

# Base configuration
Base = declarative_base()

def get_database_url():
    """Get database URL with fallback to Cloud SQL instance"""
    try:
        # Try standard PostgreSQL connection first
        primary_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        with create_engine(primary_url, connect_args={"connect_timeout": 3}).connect() as conn:
            conn.execute(text("SELECT 1"))
            return primary_url
    except Exception as e:
        print(f"Standard PostgreSQL connection failed: {e}")
        
        # Fallback to Cloud SQL instance if configured
        if CLOUD_SQL_INSTANCE:
            return f"postgresql://{DB_USER}:{DB_PASSWORD}@{CLOUD_SQL_INSTANCE}/{DB_NAME}"
        raise Exception("No valid database connection available")

# Database URL and engine configuration
try:
    DATABASE_URL = get_database_url()
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        pool_size=5,  # Reduced for Cloud Run
        max_overflow=10,
        pool_timeout=30,
        pool_pre_ping=True,
        pool_recycle=1800
    )
except Exception as e:
    print(f"Failed to initialize database: {e}")
    raise

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
            
            # Check if we're using Cloud SQL
            is_cloud_sql = CLOUD_SQL_INSTANCE in str(engine.url)
            connection_type = "Cloud SQL" if is_cloud_sql else "Standard PostgreSQL"
            
            # Check isolation level
            isolation = conn.execute(text("SHOW transaction_isolation")).scalar()
            autocommit = conn.execute(text("SHOW autocommit")).scalar()
            
            print(f"Database connected! ({connection_type})")
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
