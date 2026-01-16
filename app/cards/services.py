import json
from typing import List, Dict

from google import genai
from google.genai import types

from app.config import get_settings
from app.pdf.extractor import extract_text_from_pdf

settings = get_settings()

# Configure Gemini
client = genai.Client(api_key=settings.GEMINI_API_KEY)


async def generate_cards_from_pdf(pdf_bytes: bytes) -> List[Dict[str, str]]:
    """
    Extract text from PDF and generate Anki flashcards using Gemini.
    Returns a list of dictionaries with 'question' and 'answer' keys.
    """
    # Extract text from PDF
    text_content = extract_text_from_pdf(pdf_bytes)
    
    if not text_content.strip():
        return []
    
    # Limit text to avoid token limits (roughly 30k characters)
    # if len(text_content) > 30000:
    #     text_content = text_content[:30000]
    
    system_prompt = """
You are an automated PDF-to-Markdown extractor. Your job: given a PDF file and its extracted text layer, produce one high-quality, fully self-contained Markdown (.md) file that represents the document content in a clean and structured form. Ignore images and tables

Single output: Output only the final Markdown file content. Do not write any explanations, commentary, or extra text.

Separate each Question Answer (Fact) with a newline. (\\n)
Separate a question and an Answer with colon (:) (don't add newline between question and answer).

Use the following formatting rules:
01 Картамен жұмыс жасаудағы негізгі әдістердің бірі: картометриялық әдістер
02 Картометрия әдісімен есептелетін өлшемдер: ұзындық, аудан, көлем
03 Картографиялық құралдар: циркуль, транспортир, курвиметр, планиметр
"""

    try:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            config=types.GenerateContentConfig(system_instruction=system_prompt),
            contents=[
                types.Part.from_bytes(
                    data=pdf_bytes,
                    mime_type='application/pdf',
                ),
                text_content
                ]
            )
    
        # Clean up response if it has markdown code blocks
        if response.text.startswith("```"):
            lines = response.text.split("\n")
            response.text = "\n".join(lines[1:-1])

        cards = []
        for line in response.text.split("\n"):
            idx = line.find(":")
            if idx != -1:
                question, answer = line[:idx], line[idx+1:]
                cards.append({
                    "question": question.strip(),
                    "answer": answer.strip()
                })

        
        # Validate structure
        validated_cards = []
        for card in cards:
            if isinstance(card, dict) and "question" in card and "answer" in card:
                validated_cards.append({
                    "question": str(card["question"]),
                    "answer": str(card["answer"])
                })
        
        return validated_cards
    
    except Exception as e:
        print(f"Error generating cards: {e}")
        return []
