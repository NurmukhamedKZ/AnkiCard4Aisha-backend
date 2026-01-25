from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List


class CardBase(BaseModel):
    question: str
    answer: str


class CardCreate(CardBase):
    pass


class CardUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None


class CardResponse(CardBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: int
    deck_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class CardsExport(BaseModel):
    content: str
    filename: str


# Deck Schemas
class DeckBase(BaseModel):
    name: str


class DeckCreate(DeckBase):
    folder_id: Optional[int] = None


class DeckUpdate(BaseModel):
    name: Optional[str] = None
    folder_id: Optional[int] = None



class DeckResponse(DeckBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: int
    folder_id: Optional[int] = None
    created_at: datetime
    card_count: int = 0


class DeckWithCards(DeckResponse):
    cards: List[CardResponse] = []


# Folder Schemas
class FolderBase(BaseModel):
    name: str
    color: Optional[str] = None


class FolderCreate(FolderBase):
    color: Optional[str] = None
    parent_id: Optional[int] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    parent_id: Optional[int] = None


class FolderResponse(FolderBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    color: Optional[str] = None
    parent_id: Optional[int] = None
    created_at: datetime
    # We could include decks here, but deck list might be better separate or as simple list
    # decks: List[DeckResponse] = [] 


# Study Schemas
class StudyStats(BaseModel):
    """Statistics for a deck's study progress."""
    new: int
    to_review: int
    done: int


class StudySessionStart(BaseModel):
    """Request to start a study session."""
    deck_id: int
    mode: str  # "spaced", "fast", "quiz", "exam"


class CardReviewSubmit(BaseModel):
    """Submit a card review."""
    card_id: int
    quality: Optional[int] = None  # 0-5 for spaced repetition
    answer: Optional[str] = None  # For quiz/exam modes


class StudyCardResponse(CardResponse):
    """Card response with study metadata."""
    is_new: bool = False
    due_date: Optional[datetime] = None
