import io
import logging
from typing import List
import pypdfium2 as pdfium
import pdfplumber
import pytesseract
from PIL import Image

from .base import ExtractedPage

logger = logging.getLogger(__name__)

class PDFExtractor:
    """Extractor for digital and scanned PDFs.
    
    Uses pypdfium2 for general text extraction and rasterization.
    Uses pdfplumber to accurately extract tables.
    Uses pytesseract for OCR on scanned pages.
    """
    
    async def extract(self, file_path_or_bytes: str | bytes, **kwargs) -> list[ExtractedPage]:
        pages: list[ExtractedPage] = []
        
        # Determine internal representation for pdfium and pdfplumber
        if isinstance(file_path_or_bytes, bytes):
            pdf_bytes = file_path_or_bytes
        else:
            with open(file_path_or_bytes, "rb") as f:
                pdf_bytes = f.read()

        # Extract text and rasterize via pypdfium2
        pdf = pdfium.PdfDocument(pdf_bytes)
        
        # Extract tables via pdfplumber
        try:
            plumber_pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
        except Exception as e:
            logger.warning(f"pdfplumber failed to open PDF: {e}")
            plumber_pdf = None

        for page_idx in range(len(pdf)):
            page_num = page_idx + 1
            page = pdf[page_idx]
            
            # Extract text
            text_page = page.get_textpage()
            text = text_page.get_text_bounded()
            
            is_scanned = len(text.strip()) < 50
            
            if is_scanned:
                # OCR fallback
                logger.info(f"Page {page_num} detected as scanned. Running OCR.")
                try:
                    # Rasterize page using scale 2 for better OCR quality
                    bitmap = page.render(scale=2.0)
                    pil_image = bitmap.to_pil()
                    
                    # Run pytesseract with --psm 6 (assume uniform block of text)
                    ocr_text = pytesseract.image_to_string(pil_image, config="--psm 6")
                    if ocr_text.strip():
                        pages.append(
                            ExtractedPage(
                                page_number=page_num,
                                content=ocr_text.strip(),
                                content_type="text",
                                metadata={"is_scanned": True}
                            )
                        )
                except Exception as e:
                    logger.error(f"OCR failed on page {page_num}: {e}")
            else:
                if text.strip():
                    pages.append(
                        ExtractedPage(
                            page_number=page_num,
                            content=text.strip(),
                            content_type="text",
                            metadata={"is_scanned": False}
                        )
                    )
            
            # Extract tables using pdfplumber
            if plumber_pdf:
                try:
                    p_page = plumber_pdf.pages[page_idx]
                    tables = p_page.extract_tables()
                    for t_idx, table in enumerate(tables):
                        if not table:
                            continue
                        # Convert table to markdown
                        md_table = self._table_to_markdown(table)
                        if md_table:
                            pages.append(
                                ExtractedPage(
                                    page_number=page_num,
                                    content=md_table,
                                    content_type="table",
                                    metadata={"table_index": t_idx}
                                )
                            )
                except Exception as e:
                    logger.error(f"Table extraction failed on page {page_num}: {e}")
                    
        return pages

    def _table_to_markdown(self, table: list[list[str | None]]) -> str:
        """Simple conversion of a 2D list to a markdown table."""
        if not table or not table[0]:
            return ""
            
        # Clean rows
        cleaned_table = []
        for row in table:
            cleaned_row = [str(cell).strip().replace("\n", " ") if cell else "" for cell in row]
            cleaned_table.append(cleaned_row)
            
        header = cleaned_table[0]
        rows = cleaned_table[1:]
        
        md_lines = []
        md_lines.append("| " + " | ".join(header) + " |")
        md_lines.append("|" + "|".join(["---" for _ in header]) + "|")
        for row in rows:
            # Ensure row matches header length
            padded_row = row + [""] * (len(header) - len(row))
            md_lines.append("| " + " | ".join(padded_row[:len(header)]) + " |")
            
        return "\n".join(md_lines)
