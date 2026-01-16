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

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Anki Card Generator API",
    description="Generate Anki flashcards from PDF files using AI",
    version="1.0.0"
)

# CORS middleware
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
