
from datetime import datetime, timedelta

def calculate_next_interval(ease_factor, interval, repetitions, quality):
    """
    Copy of SM-2 Algorithm logic from card_review.py for verification.
    """
    # Update ease factor
    new_ease = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ease = max(1.3, new_ease)  # Minimum ease factor is 1.3
    
    # Calculate new interval
    if quality < 3:
        # Failed - reset to beginning
        new_repetitions = 0
        new_interval = 1
    else:
        # Passed - increase interval
        new_repetitions = repetitions + 1
        
        if new_repetitions == 1:
            new_interval = 1
        elif new_repetitions == 2:
            new_interval = 6
        else:
            new_interval = round(interval * new_ease)
    
    new_due_date = datetime.now() + timedelta(days=new_interval)
    
    return new_ease, new_interval, new_repetitions, new_due_date

def test_sm2_algorithm():
    print("Testing SM-2 Algorithm Math...")
    
    # Initial state
    ease, interval, reps = 2.5, 1, 0
    
    # Test case 1: Easy (5) first time
    ease, interval, reps, _ = calculate_next_interval(ease, interval, reps, 5)
    print(f"Easy (5) #1: Ease={ease:.2f}, Interval={interval}, Reps={reps}")
    assert reps == 1 and interval == 1
    
    # Test case 2: Easy (5) second time
    ease, interval, reps, _ = calculate_next_interval(ease, interval, reps, 5)
    print(f"Easy (5) #2: Ease={ease:.2f}, Interval={interval}, Reps={reps}")
    assert reps == 2 and interval == 6
    
    # Test case 3: OK (4) third time
    ease, interval, reps, _ = calculate_next_interval(ease, interval, reps, 4)
    print(f"OK (4) #3: Ease={ease:.2f}, Interval={interval}, Reps={reps}")
    assert reps == 3 and interval == round(6 * ease)
    
    # Test case 4: Hard (3)
    old_interval = interval
    ease, interval, reps, _ = calculate_next_interval(ease, interval, reps, 3)
    print(f"Hard (3) #4: Ease={ease:.2f}, Interval={interval}, Reps={reps}")
    assert reps == 4 and interval > 1
    
    # Test case 5: Impossible (0)
    ease, interval, reps, _ = calculate_next_interval(ease, interval, reps, 0)
    print(f"Impossible (0) #5: Ease={ease:.2f}, Interval={interval}, Reps={reps}")
    assert reps == 0 and interval == 1
    
    print("SM-2 Algorithm Math test passed!")

if __name__ == "__main__":
    test_sm2_algorithm()
