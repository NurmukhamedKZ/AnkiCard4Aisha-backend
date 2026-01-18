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
    pass


class DeckResponse(DeckBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: int
    created_at: datetime
    card_count: int = 0


class DeckWithCards(DeckResponse):
    cards: List[CardResponse] = []

