from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.cards.models import Card, Deck, CardReview


class StudyMode:
    SPACED_REPETITION = "spaced"
    FAST_REVIEW = "fast"
    QUIZ = "quiz"
    EXAM_SIMULATION = "exam"


class StudyService:
    """Service for managing study sessions across different study modes."""
    
    @staticmethod
    def get_study_stats(deck_id: int, user_id: int, db: Session) -> Dict[str, int]:
        """
        Get study statistics for a deck.
        
        Returns:
            {
                "new": count of cards never reviewed,
                "to_review": count of cards due for review,
                "done": count of cards reviewed today
            }
        """
        # Get all card IDs in the deck
        card_ids = db.query(Card.id).filter(
            Card.deck_id == deck_id,
            Card.user_id == user_id
        ).all()
        card_ids = [c[0] for c in card_ids]
        
        if not card_ids:
            return {"new": 0, "to_review": 0, "done": 0}
        
        # Count new cards (never reviewed)
        reviewed_card_ids = db.query(CardReview.card_id).filter(
            CardReview.card_id.in_(card_ids),
            CardReview.user_id == user_id
        ).distinct().all()
        reviewed_card_ids = [c[0] for c in reviewed_card_ids]
        
        new_count = len(card_ids) - len(reviewed_card_ids)
        
        # Count cards due for review (due_date <= now)
        now = datetime.now()
        to_review_count = db.query(func.count(CardReview.id)).filter(
            CardReview.card_id.in_(card_ids),
            CardReview.user_id == user_id,
            CardReview.due_date <= now
        ).scalar() or 0
        
        # Count cards reviewed today
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        done_count = db.query(func.count(CardReview.id)).filter(
            CardReview.card_id.in_(card_ids),
            CardReview.user_id == user_id,
            CardReview.last_reviewed >= today_start
        ).scalar() or 0
        
        return {
            "new": new_count,
            "to_review": to_review_count,
            "done": done_count
        }
    
    @staticmethod
    def get_next_card_spaced_repetition(deck_id: int, user_id: int, db: Session, shuffle: bool = False) -> Optional[Card]:
        """
        Get next card for spaced repetition mode.
        Priority: 1) Due cards, 2) New cards
        """
        now = datetime.now()
        
        # First, try to get a due card
        query = db.query(CardReview).join(Card).filter(
            Card.deck_id == deck_id,
            Card.user_id == user_id,
            CardReview.user_id == user_id,
            CardReview.due_date <= now
        )
        
        if shuffle:
            due_review = query.order_by(func.random()).first()
        else:
            due_review = query.order_by(CardReview.due_date.asc()).first()
        
        if due_review:
            return due_review.card
        
        # If no due cards, get a new card (never reviewed)
        reviewed_card_ids = db.query(CardReview.card_id).filter(
            CardReview.user_id == user_id
        ).distinct().subquery()
        
        new_card_query = db.query(Card).filter(
            Card.deck_id == deck_id,
            Card.user_id == user_id,
            ~Card.id.in_(reviewed_card_ids)
        )
        
        if shuffle:
            new_card = new_card_query.order_by(func.random()).first()
        else:
            new_card = new_card_query.first()
        
        return new_card
    
    @staticmethod
    def get_next_card_fast_review(deck_id: int, user_id: int, db: Session, shuffle: bool = False) -> Optional[Card]:
        """
        Get next card for fast review mode.
        Returns cards sequentially without spaced repetition logic.
        """
        # Get cards not reviewed today
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        reviewed_today_ids = db.query(CardReview.card_id).filter(
            CardReview.user_id == user_id,
            CardReview.last_reviewed >= today_start
        ).distinct().subquery()
        
        query = db.query(Card).filter(
            Card.deck_id == deck_id,
            Card.user_id == user_id,
            ~Card.id.in_(reviewed_today_ids)
        )
        
        if shuffle:
            card = query.order_by(func.random()).first()
        else:
            card = query.first()
        
        return card
    
    @staticmethod
    def get_next_card_quiz(deck_id: int, user_id: int, db: Session, session_cards: List[int] = None, shuffle: bool = True) -> Optional[Card]:
        """
        Get next card for quiz mode.
        Returns random cards from the deck, excluding already answered in session.
        """
        query = db.query(Card).filter(
            Card.deck_id == deck_id,
            Card.user_id == user_id
        )
        
        if session_cards:
            query = query.filter(~Card.id.in_(session_cards))
        
        # Get random card
        if shuffle:
            card = query.order_by(func.random()).first()
        else:
            card = query.first()
        return card
    
    @staticmethod
    def submit_review_spaced_repetition(
        card_id: int,
        user_id: int,
        quality: int,
        db: Session
    ) -> Dict:
        """
        Submit a card review for spaced repetition mode.
        
        Args:
            card_id: ID of the reviewed card
            user_id: ID of the user
            quality: Quality rating (0-5)
            db: Database session
            
        Returns:
            Updated review statistics
        """
        # Get or create CardReview
        review = db.query(CardReview).filter(
            CardReview.card_id == card_id,
            CardReview.user_id == user_id
        ).first()
        
        if not review:
            # First time reviewing this card
            review = CardReview(
                card_id=card_id,
                user_id=user_id,
                ease_factor=2.5,
                interval=1,
                repetitions=0
            )
            db.add(review)
        
        # Calculate next interval using SM-2
        new_ease, new_interval, new_reps, new_due = review.calculate_next_interval(quality)
        
        # Update review
        review.ease_factor = new_ease
        review.interval = new_interval
        review.repetitions = new_reps
        review.due_date = new_due
        review.quality = quality
        review.last_reviewed = datetime.now()
        
        db.commit()
        db.refresh(review)
        
        return {
            "next_review_in_days": new_interval,
            "ease_factor": new_ease,
            "repetitions": new_reps
        }
    
    @staticmethod
    def submit_review_fast(
        card_id: int,
        user_id: int,
        db: Session
    ) -> Dict:
        """
        Submit a card review for fast review mode.
        Simply marks as reviewed today.
        """
        # Get or create CardReview
        review = db.query(CardReview).filter(
            CardReview.card_id == card_id,
            CardReview.user_id == user_id
        ).first()
        
        if not review:
            review = CardReview(
                card_id=card_id,
                user_id=user_id,
                ease_factor=2.5,
                interval=1,
                repetitions=0,
                quality=4  # Default to "OK"
            )
            db.add(review)
        
        review.last_reviewed = datetime.now()
        
        db.commit()
        
        return {"reviewed": True}
    
    @staticmethod
    def submit_quiz_answer(
        card_id: int,
        user_id: int,
        user_answer: str,
        db: Session
    ) -> Dict:
        """
        Submit and validate a quiz answer.
        Also records the attempt for statistics.
        """
        card = db.query(Card).filter(
            Card.id == card_id,
            Card.user_id == user_id
        ).first()
        
        if not card:
            return {"error": "Card not found"}
        
        # Simple text comparison (normalize whitespace and case)
        correct = card.answer.strip().lower() == user_answer.strip().lower()
        
        # Record the review attempt
        review = db.query(CardReview).filter(
            CardReview.card_id == card_id,
            CardReview.user_id == user_id
        ).first()
        
        if not review:
            review = CardReview(
                card_id=card_id,
                user_id=user_id,
                ease_factor=2.5,
                interval=1,
                repetitions=0
            )
            db.add(review)
        
        review.last_reviewed = datetime.now()
        review.quality = 5 if correct else 0
        
        db.commit()
        
        return {
            "correct": correct,
            "expected_answer": card.answer
        }
