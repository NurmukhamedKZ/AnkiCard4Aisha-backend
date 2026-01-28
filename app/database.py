from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

settings = get_settings()

# Use psycopg3 driver - convert postgresql:// to postgresql+psycopg://
database_url = settings.DATABASE_URL
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

# Add connection pool settings with timeouts to prevent hanging
engine = create_engine(
    database_url,
    pool_pre_ping=True,  # Check connection health before using
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,  # Timeout when getting connection from pool (seconds)
    connect_args={
        "connect_timeout": "10",  # Connection timeout for psycopg3 (string value in seconds)
    }
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
