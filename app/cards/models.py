from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timedelta

from app.database import Base


class Deck(Base):
    __tablename__ = "decks"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(Integer, ForeignKey("folders.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="decks")
    folder = relationship("Folder", back_populates="decks")
    cards = relationship("Card", back_populates="deck", cascade="all, delete-orphan")


class Folder(Base):
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    color = Column(String(50), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(Integer, ForeignKey("folders.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    owner = relationship("User", back_populates="folders")
    decks = relationship("Deck", back_populates="folder")
    children = relationship("Folder", back_populates="parent", cascade="all, delete-orphan")
    parent = relationship("Folder", back_populates="children", remote_side=[id])


class Card(Base):
    __tablename__ = "cards"
    
    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    deck_id = Column(Integer, ForeignKey("decks.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="cards")
    deck = relationship("Deck", back_populates="cards")
    reviews = relationship("CardReview", back_populates="card", cascade="all, delete-orphan")


class CardReview(Base):
    """
    Tracks spaced repetition data for cards using the SM-2 algorithm.
    """
    __tablename__ = "card_reviews"
    
    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # SM-2 Algorithm fields
    ease_factor = Column(Float, default=2.5, nullable=False)  # Initial ease factor
    interval = Column(Integer, default=1, nullable=False)  # Days until next review
    repetitions = Column(Integer, default=0, nullable=False)  # Consecutive correct answers
    
    # Review scheduling
    due_date = Column(DateTime(timezone=True), nullable=True)  # When card is due for review
    last_reviewed = Column(DateTime(timezone=True), server_default=func.now())
    
    # Quality of last response (0-5)
    quality = Column(Integer, CheckConstraint('quality >= 0 AND quality <= 5'), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    card = relationship("Card", back_populates="reviews")
    user = relationship("User")

    def calculate_next_interval(self, quality: int) -> tuple:
        """
        Calculate next review interval using SM-2 algorithm.
        
        Args:
            quality: Response quality (0-5)
                0 = Impossible
                3 = Hard
                4 = OK
                5 = Easy
        
        Returns:
            tuple of (new_ease_factor, new_interval_days, new_repetitions, new_due_date)
        """
        # Update ease factor
        new_ease = self.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        new_ease = max(1.3, new_ease)  # Minimum ease factor is 1.3
        
        # Calculate new interval
        if quality < 3:
            # Failed - reset to beginning
            new_repetitions = 0
            new_interval = 1
        else:
            # Passed - increase interval
            new_repetitions = self.repetitions + 1
            
            if new_repetitions == 1:
                new_interval = 1
            elif new_repetitions == 2:
                new_interval = 6
            else:
                new_interval = round(self.interval * new_ease)
        
        # Calculate due date
        new_due_date = datetime.now() + timedelta(days=new_interval)
        
        return new_ease, new_interval, new_repetitions, new_due_date

