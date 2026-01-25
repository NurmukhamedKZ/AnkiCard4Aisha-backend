from typing import List

import fitz


def extract_text_from_pdf(pdf_bytes: bytes, pages_per_chunk: int = 1) -> List[str]:
    """
    Extract text from PDF, grouping pages into chunks.
    
    Args:
        pdf_bytes: The PDF file as bytes
        pages_per_chunk: Number of pages to combine into each text chunk
    
    Returns:
        List of text strings, one per chunk
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = doc.page_count
    result_list = []
    
    for i in range(0, total_pages, pages_per_chunk):
        text_chunk = []
        for j in range(i, min(i + pages_per_chunk, total_pages)):
            page = doc.load_page(j)
            text_chunk.append(page.get_text("text"))
        result_list.append("\n\n".join(text_chunk))
    
    doc.close()
    return result_list


def split_pdf_bytes_to_chunks(pdf_bytes: bytes, pages_per_chunk: int = 1) -> List[bytes]:
    """
    Splits PDF bytes into a list of byte objects, each containing N pages.
    
    Args:
        pdf_bytes: The PDF file as bytes
        pages_per_chunk: Number of pages per chunk
    
    Returns:
        List of PDF byte objects, one per chunk
    """
    src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = src_doc.page_count
    chunks = []

    for i in range(0, total_pages, pages_per_chunk):
        new_doc = fitz.open()
        
        start = i
        end = min(i + pages_per_chunk - 1, total_pages - 1)
        
        new_doc.insert_pdf(src_doc, from_page=start, to_page=end)
        
        chunk_bytes = new_doc.tobytes()
        chunks.append(chunk_bytes)
        
        new_doc.close()

    src_doc.close()
    return chunks


def filter_pdf_pages(pdf_bytes: bytes, page_indices: List[int]) -> bytes:
    """
    Creates a new PDF containing only the specified pages.
    
    Args:
        pdf_bytes: The original PDF bytes
        page_indices: List of 0-based page indices to include
        
    Returns:
        Bytes of the new filtered PDF
    """
    if not page_indices:
        return pdf_bytes
        
    src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    new_doc = fitz.open()
    
    # Sort indices to maintain order and remove duplicates
    sorted_indices = sorted(list(set(page_indices)))
    
    # Validate indices
    valid_indices = [i for i in sorted_indices if 0 <= i < src_doc.page_count]
    
    if not valid_indices:
        src_doc.close()
        new_doc.close()
        return pdf_bytes
        
    # Select specific pages into the new document
    # insert_pdf allows copying pages from source to destination
    # We can iterate and copy one by one, or if we want to copy a set of disparate pages:
    # We can use new_doc.insert_pdf(src_doc, from_page=i, to_page=i) for each i in valid_indices.
    for i in valid_indices:
        new_doc.insert_pdf(src_doc, from_page=i, to_page=i)
    
    result_bytes = new_doc.tobytes()
    
    src_doc.close()
    new_doc.close()
    
    return result_bytes