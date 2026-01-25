
from sqlalchemy import create_engine, text
from app.config import get_settings

def migrate():
    settings = get_settings()
    database_url = settings.DATABASE_URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    
    engine = create_engine(database_url)
    
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        print("Starting migration...")
        
        # Ensure tables exist (specifically folders)
        from app.database import Base, engine as db_engine
        from app.cards import models # Register models
        Base.metadata.create_all(bind=db_engine)
        print("Tables created (if missing).")
        
        print("Adding folder_id column to decks table...")
        try:
            conn.execute(text("ALTER TABLE decks ADD COLUMN folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL;"))
            print("Column added successfully.")
        except Exception as e:
            print(f"Column addition might have failed (maybe already exists?): {e}")

        print("Adding color column to folders table...")
        try:
            conn.execute(text("ALTER TABLE folders ADD COLUMN color VARCHAR(50);"))
            print("Color column added successfully.")
        except Exception as e:
            print(f"Column addition might have failed (maybe already exists?): {e}")

if __name__ == "__main__":
    migrate()
