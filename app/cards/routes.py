from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func

from app.database import get_db
from app.auth.utils import get_current_user
from app.users.models import User
from app.cards.models import Card, Deck
from app.cards.schemas import CardCreate, CardUpdate, CardResponse, DeckResponse, DeckCreate
from app.cards.services import generate_cards_from_pdf

router = APIRouter(prefix="/cards", tags=["Cards"])


# ============== DECK ENDPOINTS ==============

@router.get("/decks", response_model=List[DeckResponse])
async def get_decks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all decks for the current user."""
    decks = db.query(Deck).filter(Deck.user_id == current_user.id).order_by(Deck.created_at.desc()).all()
    
    # Add card count to each deck
    result = []
    for deck in decks:
        card_count = db.query(sql_func.count(Card.id)).filter(Card.deck_id == deck.id).scalar()
        deck_dict = {
            "id": deck.id,
            "name": deck.name,
            "user_id": deck.user_id,
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
    
    lines = []
    for card in cards:
        question = card.question.replace(";", "\\;")
        answer = card.answer.replace(";", "\\;")
        lines.append(f"{question};{answer}")
    
    content = "\n".join(lines)
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a PDF file and generate Anki cards from it."""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed"
        )
    
    
    
    # Read PDF content
    pdf_bytes = await file.read()
    
    if len(pdf_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded"
        )
    
    # Create deck with PDF filename
    deck_name = file.filename.rsplit('.', 1)[0]  # Remove .pdf extension
    deck = Deck(name=deck_name, user_id=current_user.id)
    db.add(deck)
    db.flush()  # Get deck ID without committing
    
    # Generate cards using Gemini
    generated_cards = await generate_cards_from_pdf(pdf_bytes)
    
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
    
    lines = []
    for card in cards:
        question = card.question.replace(";", "\\;")
        answer = card.answer.replace(";", "\\;")
        lines.append(f"{question};{answer}")
    
    content = "\n".join(lines)
    
    return PlainTextResponse(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=anki_cards.txt"}
    )
