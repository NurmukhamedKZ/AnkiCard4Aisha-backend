import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, engine
from app.auth.routes import router as auth_router
from app.cards.routes import router as cards_router

# Import models so SQLAlchemy can create tables
from app.users.models import User
from app.cards.models import Card

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup: Create database tables
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        # Don't crash the app - let it start and handle errors per-request
    yield
    # Shutdown: cleanup if needed
    logger.info("Application shutting down")


app = FastAPI(
    title="Anki Card Generator API",
    description="Generate Anki flashcards from PDF files using AI",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware - must be first to handle OPTIONS requests quickly
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(cards_router)


@app.get("/")
async def root():
    return {"message": "Anki Card Generator API", "status": "running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
