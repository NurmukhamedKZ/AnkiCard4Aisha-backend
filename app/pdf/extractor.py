import fitz


def extract_text_from_pdf(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    text_list = "\n\n".join([doc.load_page(page_num).get_text("text") for page_num in range(len(doc))])
    
    return text_list