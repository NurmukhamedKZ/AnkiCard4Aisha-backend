"""Add CardReview model for spaced repetition

This script creates the card_reviews table for tracking spaced repetition data.
Run with: python migrate_card_reviews.py
"""

from app.database import engine, Base
from app.cards.models import Card, Deck, Folder, CardReview
from app.users.models import User

def migrate():
    """Create the card_reviews table."""
    print("Creating card_reviews table...")
    Base.metadata.create_all(bind=engine, tables=[CardReview.__table__])
    print("✓ card_reviews table created successfully!")

if __name__ == "__main__":
    migrate()
