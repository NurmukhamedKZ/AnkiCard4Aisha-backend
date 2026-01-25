from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Form, Body
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func
from pydantic import BaseModel

from app.database import get_db
from app.auth.utils import get_current_user
from app.users.models import User
from app.cards.models import Card, Deck, Folder
from app.cards.schemas import CardCreate, CardUpdate, CardResponse, DeckResponse, DeckCreate, DeckUpdate, FolderCreate, FolderUpdate, FolderResponse
from app.cards.services import generate_cards_from_pdf
from app.cards.import_services import (
    parse_csv_cards,
    generate_cards_from_text,
    extract_and_generate_from_pptx,
    parse_anki_package
)

router = APIRouter(prefix="/cards", tags=["Cards"])

# Constants
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


def escape_csv_field(text: str) -> str:
    """Escape semicolons in text for CSV export."""
    return text.replace(";", "\\;")


def format_cards_for_export(cards: List[Card]) -> str:
    """Format cards as semicolon-separated text."""
    lines = []
    for card in cards:
        question = escape_csv_field(card.question)
        answer = escape_csv_field(card.answer)
        lines.append(f"{question};{answer}")
    return "\n".join(lines)


# ============== DECK ENDPOINTS ==============

@router.get("/decks", response_model=List[DeckResponse])
async def get_decks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all decks for the current user."""
    # Optimized query with card count subquery to avoid N+1
    card_count_subq = (
        db.query(Card.deck_id, sql_func.count(Card.id).label("card_count"))
        .group_by(Card.deck_id)
        .subquery()
    )
    
    decks_with_counts = (
        db.query(Deck, sql_func.coalesce(card_count_subq.c.card_count, 0).label("card_count"))
        .outerjoin(card_count_subq, Deck.id == card_count_subq.c.deck_id)
        .filter(Deck.user_id == current_user.id)
        .order_by(Deck.created_at.desc())
        .all()
    )
    
    result = []
    for deck, card_count in decks_with_counts:
        deck_dict = {
            "id": deck.id,
            "name": deck.name,
            "user_id": deck.user_id,
            "folder_id": deck.folder_id,
            "created_at": deck.created_at,
            "card_count": card_count
        }
        result.append(deck_dict)
    
    return result


@router.delete("/decks/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deck(
    deck_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a deck and all its cards."""
    deck = db.query(Deck).filter(Deck.id == deck_id, Deck.user_id == current_user.id).first()
    if not deck:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deck not found"
        )
    
    db.delete(deck)
    db.commit()
    return None


@router.put("/decks/{deck_id}", response_model=DeckResponse)
async def update_deck(
    deck_id: int,
    deck_update: DeckUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a deck (name or folder)."""
    deck = db.query(Deck).filter(Deck.id == deck_id, Deck.user_id == current_user.id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    
    if deck_update.folder_id is not None:
        # Verify folder exists and belongs to user
        if deck_update.folder_id > 0:
            folder = db.query(Folder).filter(Folder.id == deck_update.folder_id, Folder.user_id == current_user.id).first()
            if not folder:
                 raise HTTPException(status_code=404, detail="Folder not found")
            deck.folder_id = deck_update.folder_id
        else:
            # If 0 (or negative), remove from folder
            deck.folder_id = None
            
    if deck_update.name is not None:
        deck.name = deck_update.name
    
    db.commit()
    db.refresh(deck)
    return deck

# ============== FOLDER ENDPOINTS ==============

@router.post("/folders", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    folder: FolderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new folder."""
    db_folder = Folder(name=folder.name, color=folder.color, parent_id=folder.parent_id, user_id=current_user.id)
    db.add(db_folder)
    db.commit()
    db.refresh(db_folder)
    return db_folder


@router.put("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: int,
    folder_data: FolderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a folder (rename, change color, move)."""
    db_folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == current_user.id).first()
    if not db_folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    # Check for circular reference if moving
    if folder_data.parent_id is not None:
        if folder_data.parent_id == folder_id:
            raise HTTPException(status_code=400, detail="Cannot move folder inside itself")
        # TODO: Deep circular check if needed, but simple one covers basic "move into self"
        
        # Verify parent exists
        parent = db.query(Folder).filter(Folder.id == folder_data.parent_id, Folder.user_id == current_user.id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent folder not found")

    if folder_data.name is not None:
        db_folder.name = folder_data.name
    if folder_data.color is not None:
        db_folder.color = folder_data.color
    if folder_data.parent_id is not None:  # explicit move, can be None (root) or int
        # To handle moving to root, client should probably pass explicit null, 
        # but pydantic optional defaults to None which means "no change".
        # We need a way to unset parent_id. 
        # For now, let's assume client sends -1 or similar for root if we want that, 
        # or we accept that 'None' in Update schema means 'No Change'.
        # If we want to move to root, maybe special value?
        # Let's check schema again. `parent_id: Optional[int]`.
        # Standard pattern: use separate field or explicit reset logic.
        # For simplicity, if passed (not None in dict), update it.
        # But Pydantic exclude_unset=True is needed in client or manual check.
        # We are manually checking `if folder_data.parent_id is not None`.
        # This prevents unsetting parent_id (moving to root). 
        # User needs to move to root. Let's assume 0 = root? Or special string?
        # Or standard FastAPI `exclude_unset` usage.
        # Let's iterate over `folder_data.dict(exclude_unset=True)`.
        pass

    # Better update logic using exclude_unset
    update_data = folder_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_folder, field, value)

    db.commit()
    db.refresh(db_folder)
    return db_folder


@router.get("/folders", response_model=List[FolderResponse])
async def get_folders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all folders for the current user."""
    return db.query(Folder).filter(Folder.user_id == current_user.id).all()


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a folder. encapsulated decks will become orphans (null folder_id) or deleted?
       Model says: folder_id = Column(..., ondelete="SET NULL")
       So decks will just lose their folder assignment.
    """
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == current_user.id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    db.delete(folder)
    db.commit()
    return None


@router.get("/decks/{deck_id}/export", response_class=PlainTextResponse)
async def export_deck(
    deck_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export all cards from a deck as semicolon-separated text file."""
    from urllib.parse import quote
    
    deck = db.query(Deck).filter(Deck.id == deck_id, Deck.user_id == current_user.id).first()
    if not deck:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deck not found"
        )
    
    cards = db.query(Card).filter(Card.deck_id == deck_id).order_by(Card.created_at.desc()).all()
    
    if not cards:
        return PlainTextResponse(content="", media_type="text/plain")
    
    content = format_cards_for_export(cards)
    # Use URL encoding for non-ASCII characters in filename
    safe_name = quote(deck.name.replace(' ', '_'), safe='')
    filename = f"{safe_name}_cards.txt"
    
    return PlainTextResponse(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"}
    )



# ============== CARD ENDPOINTS ==============

@router.post("/upload", response_model=List[CardResponse], status_code=status.HTTP_201_CREATED)
async def upload_pdf(
    file: UploadFile = File(...),
    pages: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a PDF file and generate Anki cards from it.
    
    - **file**: The PDF file
    - **pages**: Optional, comma-separated list of 0-based page indices to process (e.g., "0,1,3")
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed"
        )
    
    # Read PDF content
    pdf_bytes = await file.read()

    # Parse selected pages
    selected_page_indices = None
    if pages:
        try:
            # pages comes as "1,2,3" string from frontend
            # Assuming frontend sends 1-based or 0-based? Let's assume 1-based keys from UI, or convert.
            # Usually UI displays 1-based, but internally we might want 0-based for fitz.
            # Let's standardize: Frontend sends comma-separated integers. 
            # If the user sees "Page 1", we treat it as index 0.
            # Let's assume the frontend sends 0-BASED INDICES for simplicity in backend logic, 
            # OR we decode here.
            # Let's assume frontend sends 0-based indices.
            selected_page_indices = [int(p.strip()) for p in pages.split(",") if p.strip().isdigit()]
        except ValueError:
            pass # Ignore invalid format and process all pages
    
    # Validate file size
    if len(pdf_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded"
        )
    
    if len(pdf_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB"
        )
    
    # Create deck with PDF filename
    deck_name = file.filename.rsplit('.', 1)[0]  # Remove .pdf extension
    deck = Deck(name=deck_name, user_id=current_user.id)
    db.add(deck)
    db.flush()  # Get deck ID without committing
    
    # Generate cards using Gemini
    try:
        generated_cards = await generate_cards_from_pdf(pdf_bytes, selected_pages=selected_page_indices)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error processing PDF: {str(e)}"
        )
    
    if not generated_cards:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not generate cards from the PDF. The file might be empty or contain unsupported content."
        )
    
    # Save cards to database
    created_cards = []
    for card_data in generated_cards:
        card = Card(
            question=card_data["question"],
            answer=card_data["answer"],
            user_id=current_user.id,
            deck_id=deck.id
        )
        db.add(card)
        created_cards.append(card)
    
    db.commit()
    
    # Refresh to get IDs and timestamps
    for card in created_cards:
        db.refresh(card)
    
    return created_cards


@router.get("/", response_model=List[CardResponse])
async def get_cards(
    deck_id: Optional[int] = Query(None, description="Filter by deck ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all cards for the current user, optionally filtered by deck."""
    query = db.query(Card).filter(Card.user_id == current_user.id)
    
    if deck_id is not None:
        query = query.filter(Card.deck_id == deck_id)
    
    cards = query.order_by(Card.created_at.desc()).all()
    return cards


@router.get("/{card_id}", response_model=CardResponse)
async def get_card(
    card_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific card by ID."""
    card = db.query(Card).filter(Card.id == card_id, Card.user_id == current_user.id).first()
    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Card not found"
        )
    return card


@router.put("/{card_id}", response_model=CardResponse)
async def update_card(
    card_id: int,
    card_update: CardUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a card."""
    card = db.query(Card).filter(Card.id == card_id, Card.user_id == current_user.id).first()
    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Card not found"
        )
    
    if card_update.question is not None:
        card.question = card_update.question
    if card_update.answer is not None:
        card.answer = card_update.answer
    
    db.commit()
    db.refresh(card)
    return card


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(
    card_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a card."""
    card = db.query(Card).filter(Card.id == card_id, Card.user_id == current_user.id).first()
    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Card not found"
        )
    
    db.delete(card)
    db.commit()
    return None


@router.get("/export/txt", response_class=PlainTextResponse)
async def export_cards(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export all cards as semicolon-separated text file."""
    cards = db.query(Card).filter(Card.user_id == current_user.id).order_by(Card.created_at.desc()).all()
    
    if not cards:
        return PlainTextResponse(content="", media_type="text/plain")
    
    content = format_cards_for_export(cards)
    
    return PlainTextResponse(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=anki_cards.txt"}
    )


# ============== NEW IMPORT/GENERATE ENDPOINTS ==============

# Pydantic models for request bodies
class CSVImportRequest(BaseModel):
    cards: List[Dict[str, str]]  # [{"front": "Q", "back": "A"}, ...]
    deck_name: str


class TextGenerateRequest(BaseModel):
    text: str
    deck_name: str


@router.post("/decks", response_model=DeckResponse, status_code=status.HTTP_201_CREATED)
async def create_deck(
    deck: DeckCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new empty deck."""
    # Verify folder exists if folder_id is provided
    if deck.folder_id is not None:
        folder = db.query(Folder).filter(
            Folder.id == deck.folder_id,
            Folder.user_id == current_user.id
        ).first()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

    db_deck = Deck(name=deck.name, folder_id=deck.folder_id, user_id=current_user.id)
    db.add(db_deck)
    db.commit()
    db.refresh(db_deck)
    
    # Return with card_count = 0
    return {
        "id": db_deck.id,
        "name": db_deck.name,
        "user_id": db_deck.user_id,
        "folder_id": db_deck.folder_id,
        "created_at": db_deck.created_at,
        "card_count": 0
    }


@router.post("/import/csv", response_model=List[CardResponse], status_code=status.HTTP_201_CREATED)
async def import_csv(
    import_request: CSVImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Import cards from CSV/Quizlet data (pre-parsed by frontend).
    """
    if not import_request.cards:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No cards provided"
        )
    
    # Parse cards
    parsed_cards = parse_csv_cards(import_request.cards)
    
    if not parsed_cards:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid cards found in the data"
        )
    
    # Create deck
    deck = Deck(name=import_request.deck_name, user_id=current_user.id)
    db.add(deck)
    db.flush()
    
    # Create cards
    created_cards = []
    for card_data in parsed_cards:
        card = Card(
            question=card_data["question"],
            answer=card_data["answer"],
            user_id=current_user.id,
            deck_id=deck.id
        )
        db.add(card)
        created_cards.append(card)
    
    db.commit()
    
    # Refresh to get IDs
    for card in created_cards:
        db.refresh(card)
    
    return created_cards


@router.post("/generate/text", response_model=List[CardResponse], status_code=status.HTTP_201_CREATED)
async def generate_from_text(
    generate_request: TextGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate flashcards from plain text using AI.
    """
    if not generate_request.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text content is required"
        )
    
    # Generate cards using Gemini
    try:
        generated_cards = await generate_cards_from_text(generate_request.text)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error generating cards: {str(e)}"
        )
    
    if not generated_cards:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not generate cards from the text. Please try with different content."
        )
    
    # Create deck
    deck = Deck(name=generate_request.deck_name, user_id=current_user.id)
    db.add(deck)
    db.flush()
    
    # Save cards
    created_cards = []
    for card_data in generated_cards:
        card = Card(
            question=card_data["question"],
            answer=card_data["answer"],
            user_id=current_user.id,
            deck_id=deck.id
        )
        db.add(card)
        created_cards.append(card)
    
    db.commit()
    
    for card in created_cards:
        db.refresh(card)
    
    return created_cards


@router.post("/import/pptx", response_model=List[CardResponse], status_code=status.HTTP_201_CREATED)
async def import_pptx(
    file: UploadFile = File(...),
    deck_name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Import PowerPoint file and generate flashcards using AI.
    """
    if not file.filename.lower().endswith(('.pptx', '.ppt')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PowerPoint files (.pptx, .ppt) are allowed"
        )
    
    # Read file content
    pptx_bytes = await file.read()
    
    if len(pptx_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded"
        )
    
    if len(pptx_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB"
        )
    
    # Extract and generate cards
    try:
        generated_cards = await extract_and_generate_from_pptx(pptx_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error processing PowerPoint: {str(e)}"
        )
    
    if not generated_cards:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not generate cards from PowerPoint. The file might be empty or contain unsupported content."
        )
    
    # Create deck
    deck = Deck(name=deck_name, user_id=current_user.id)
    db.add(deck)
    db.flush()
    
    # Save cards
    created_cards = []
    for card_data in generated_cards:
        card = Card(
            question=card_data["question"],
            answer=card_data["answer"],
            user_id=current_user.id,
            deck_id=deck.id
        )
        db.add(card)
        created_cards.append(card)
    
    db.commit()
    
    for card in created_cards:
        db.refresh(card)
    
    return created_cards


@router.post("/import/anki", response_model=List[CardResponse], status_code=status.HTTP_201_CREATED)
async def import_anki(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Import Anki .apkg file.
    
    NOTE: This is a simplified implementation. Full Anki import is complex.
    """
    if not file.filename.lower().endswith('.apkg'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Anki .apkg files are allowed"
        )
    
    # Read file
    apkg_bytes = await file.read()
    
    if len(apkg_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded"
        )
    
    # Parse Anki package
    try:
        decks_data = parse_anki_package(apkg_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error parsing Anki package: {str(e)}"
        )
    
    if not decks_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No decks found in Anki package"
        )
    
    # Import all decks
    all_created_cards = []
    
    for deck_name, cards_data in decks_data.items():
        # Create deck
        deck = Deck(name=deck_name, user_id=current_user.id)
        db.add(deck)
        db.flush()
        
        # Create cards
        for card_data in cards_data:
            card = Card(
                question=card_data["question"],
                answer=card_data["answer"],
                user_id=current_user.id,
                deck_id=deck.id
            )
            db.add(card)
            all_created_cards.append(card)
    
    db.commit()
    
    for card in all_created_cards:
        db.refresh(card)
    
    return all_created_cards

# ============== STUDY ENDPOINTS ==============

@router.get("/study/{deck_id}/stats", response_model=dict)
async def get_study_stats(
    deck_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get study statistics for a deck."""
    from app.cards.study_service import StudyService
    
    # Verify deck belongs to user
    deck = db.query(Deck).filter(Deck.id == deck_id, Deck.user_id == current_user.id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    
    stats = StudyService.get_study_stats(deck_id, current_user.id, db)
    return stats


@router.post("/study/next", response_model=Optional[dict])
async def get_next_study_card(
    deck_id: int = Body(..., embed=True),
    mode: str = Body(..., embed=True),
    session_cards: Optional[List[int]] = Body(None, embed=True),
    shuffle: bool = Body(False, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the next card to study based on the selected mode.
    
    - **deck_id**: ID of the deck to study
    - **mode**: Study mode ("spaced", "fast", "quiz", "exam")
    - **session_cards**: List of card IDs already seen in this session (for quiz/exam)
    - **shuffle**: Whether to randomize card selection
    """
    from app.cards.study_service import StudyService, StudyMode
    from app.cards.models import CardReview
    
    # Verify deck belongs to user
    deck = db.query(Deck).filter(Deck.id == deck_id, Deck.user_id == current_user.id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    
    # Get next card based on mode
    if mode == StudyMode.SPACED_REPETITION:
        card = StudyService.get_next_card_spaced_repetition(deck_id, current_user.id, db, shuffle=shuffle)
    elif mode == StudyMode.FAST_REVIEW:
        card = StudyService.get_next_card_fast_review(deck_id, current_user.id, db, shuffle=shuffle)
    elif mode in [StudyMode.QUIZ, StudyMode.EXAM_SIMULATION]:
        card = StudyService.get_next_card_quiz(deck_id, current_user.id, db, session_cards or [], shuffle=shuffle)
    else:
        raise HTTPException(status_code=400, detail="Invalid study mode")
    
    if not card:
        return None
    
    # Check if card is new (never reviewed)
    review = db.query(CardReview).filter(
        CardReview.card_id == card.id,
        CardReview.user_id == current_user.id
    ).first()
    
    is_new = review is None
    due_date = review.due_date if review else None
    
    return {
        "id": card.id,
        "question": card.question,
        "answer": card.answer,
        "user_id": card.user_id,
        "deck_id": card.deck_id,
        "created_at": card.created_at,
        "updated_at": card.updated_at,
        "is_new": is_new,
        "due_date": due_date
    }


@router.post("/study/review", response_model=dict)
async def submit_study_review(
    card_id: int = Body(..., embed=True),
    mode: str = Body(..., embed=True),
    quality: Optional[int] = Body(None, embed=True),
    answer: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Submit a card review.
    
    - **card_id**: ID of the reviewed card
    - **mode**: Study mode ("spaced", "fast", "quiz", "exam")
    - **quality**: Quality rating 0-5 (for spaced repetition)
    - **answer**: User's answer (for quiz/exam modes)
    """
    from app.cards.study_service import StudyService, StudyMode
    
    # Verify card belongs to user
    card = db.query(Card).filter(Card.id == card_id, Card.user_id == current_user.id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    # Process based on mode
    if mode == StudyMode.SPACED_REPETITION:
        if quality is None:
            raise HTTPException(status_code=400, detail="Quality rating required for spaced repetition")
        if quality < 0 or quality > 5:
            raise HTTPException(status_code=400, detail="Quality must be between 0 and 5")
        
        result = StudyService.submit_review_spaced_repetition(card_id, current_user.id, quality, db)
        return {"success": True, **result}
    
    elif mode == StudyMode.FAST_REVIEW:
        result = StudyService.submit_review_fast(card_id, current_user.id, db)
        return {"success": True, **result}
    
    elif mode in [StudyMode.QUIZ, StudyMode.EXAM_SIMULATION]:
        if answer is None:
            raise HTTPException(status_code=400, detail="Answer required for quiz/exam mode")
        
        result = StudyService.submit_quiz_answer(card_id, current_user.id, answer, db)
        return {"success": True, **result}
    
    else:
        raise HTTPException(status_code=400, detail="Invalid study mode")

