import fitz


def extract_text_from_pdf(pdf_bytes, pages_per_chunk=1):
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

    # text_list = [doc.load_page(page_num).get_text("text") for page_num in range(len(doc))]
    
    # return text_list

def split_pdf_bytes_to_chunks(pdf_bytes, pages_per_chunk=1):
    """
    Splits PDF bytes into a list of byte objects, each containing N pages.
    """
    # Open the PDF from bytes
    src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = src_doc.page_count
    chunks = []

    for i in range(0, total_pages, pages_per_chunk):
        # Create a new empty PDF
        new_doc = fitz.open()
        
        # Determine the range of pages for this chunk
        start = i
        end = min(i + pages_per_chunk - 1, total_pages - 1)
        
        # Copy pages from source to the new document
        new_doc.insert_pdf(src_doc, from_page=start, to_page=end)
        
        # Save the new document back into a byte object
        chunk_bytes = new_doc.tobytes()
        chunks.append(chunk_bytes)
        
        new_doc.close()

    src_doc.close()
    return chunks