from sqlalchemy import text
from app.database import engine

def migrate():
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        print("Starting migration for reviews...")
        
        print("Creating card_reviews table if not exists...")
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS card_reviews (
                    id SERIAL PRIMARY KEY,
                    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                    quality INTEGER NOT NULL,
                    reviewed_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                    interval INTEGER,
                    ease_factor INTEGER
                );
            """))
            print("Table created successfully.")
        except Exception as e:
            print(f"Table creation failed: {e}")

if __name__ == "__main__":
    migrate()
