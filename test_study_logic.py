
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.cards.models import CardReview, Card, Deck
from app.database import Base
# Import all models to satisfy relationships
from app.users.models import User if os.path.exists("backend/app/users/models.py") else object


def test_sm2_algorithm():
    print("Testing SM-2 Algorithm...")
    review = CardReview(ease_factor=2.5, interval=1, repetitions=0)
    
    # Test case: Easy (5)
    new_ease, new_interval, new_reps, new_due = review.calculate_next_interval(5)
    print(f"Easy (5): Ease={new_ease:.2f}, Interval={new_interval}, Reps={new_reps}")
    assert new_reps == 1
    assert new_interval == 1
    
    # Update for next iteration
    review.ease_factor = new_ease
    review.interval = new_interval
    review.repetitions = new_reps
    
    # Test case: Easy (5) again
    new_ease, new_interval, new_reps, new_due = review.calculate_next_interval(5)
    print(f"Easy (5) again: Ease={new_ease:.2f}, Interval={new_interval}, Reps={new_reps}")
    assert new_reps == 2
    assert new_interval == 6
    
    # Update for next iteration
    review.ease_factor = new_ease
    review.interval = new_interval
    review.repetitions = new_reps
    
    # Test case: OK (4)
    new_ease, new_interval, new_reps, new_due = review.calculate_next_interval(4)
    print(f"OK (4): Ease={new_ease:.2f}, Interval={new_interval}, Reps={new_reps}")
    assert new_reps == 3
    assert new_interval == round(6 * new_ease)

    # Test case: Impossible (0)
    new_ease, new_interval, new_reps, new_due = review.calculate_next_interval(0)
    print(f"Impossible (0): Ease={new_ease:.2f}, Interval={new_interval}, Reps={new_reps}")
    assert new_reps == 0
    assert new_interval == 1
    
    print("SM-2 Algorithm test passed!")

if __name__ == "__main__":
    test_sm2_algorithm()
