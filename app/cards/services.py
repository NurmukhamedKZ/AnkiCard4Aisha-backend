import logging
from typing import List, Dict, Optional

from google import genai
from google.genai import types

from app.config import get_settings
from app.pdf.extractor import extract_text_from_pdf
from app.pdf.extractor import split_pdf_bytes_to_chunks

logger = logging.getLogger(__name__)

settings = get_settings()

# Configure Gemini
client = genai.Client(api_key=settings.GEMINI_API_KEY)


def query_to_llm(pdf_bytes: bytes, pdf_text: str) -> Optional[str]:
    """
    Query Gemini LLM to extract flashcards from PDF.
    
    Returns the response text or None on error.
    """
    system_prompt = """
You are an automated PDF-to-Markdown extractor. Your job: given a PDF file and its extracted text layer, produce one high-quality, fully self-contained Markdown (.md) file that represents the document content in a clean and structured form. Ignore images, question numbers, and tables

Single output: Output only the final Markdown file content. Do not write any explanations, commentary, or extra text.

Separate each Question Answer (Fact) with a newline. (\\n)
Separate a question and an Answer with colon (:) (don't add newline between question and answer).

Use the following formatting rules:
Картамен жұмыс жасаудағы негізгі әдістердің бірі: картометриялық әдістер
Картометрия әдісімен есептелетін өлшемдер: ұзындық, аудан, көлем
Картографиялық құралдар: циркуль, транспортир, курвиметр, планиметр
"""

    try:
        logger.info("Querying Gemini LLM...")
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            config=types.GenerateContentConfig(system_instruction=system_prompt),
            contents=[
                types.Part.from_bytes(
                    data=pdf_bytes,
                    mime_type='application/pdf',
                ),
                pdf_text
            ]
        )
        logger.info("Received response from Gemini LLM.")
        return response.text
    except Exception as e:
        logger.error(f"Error querying Gemini: {e}")
        return None


async def generate_cards_from_pdf(pdf_bytes: bytes) -> List[Dict[str, str]]:
    """
    Extract text from PDF and generate Anki flashcards using Gemini.
    Returns a list of dictionaries with 'question' and 'answer' keys.
    """
    # Extract text from PDF
    text_content_list = extract_text_from_pdf(pdf_bytes, pages_per_chunk=10)
    logger.info(f"Extracted {len(text_content_list)} text chunks from PDF.")
    
    if not text_content_list:
        return []
    
    if len(text_content_list) == 1:
        logger.info("Single chunk detected, querying LLM...")
        response = query_to_llm(pdf_bytes, text_content_list[0])
        if response is None:
            return []
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1])
    else:
        logger.info("Multiple chunks detected, querying LLM for each chunk...")
        chunk_bytes = split_pdf_bytes_to_chunks(pdf_bytes, pages_per_chunk=10)
        full_response = ""
        for chunk_byte, chunk_text in zip(chunk_bytes, text_content_list, strict=True):
            chunk_response = query_to_llm(chunk_byte, chunk_text)
            if chunk_response is None:
                continue
            
            if chunk_response.startswith("```"):
                lines = chunk_response.split("\n")
                chunk_response = "\n".join(lines[1:-1])

            full_response += chunk_response + "\n"
        response = full_response

    # Parse response into cards
    cards = []
    for line in response.split("\n"):
        idx = line.find(":")
        if idx != -1:
            question, answer = line[:idx], line[idx+1:]
            question = question.strip()
            answer = answer.strip()
            if question and answer:  # Skip empty entries
                cards.append({
                    "question": question,
                    "answer": answer
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

