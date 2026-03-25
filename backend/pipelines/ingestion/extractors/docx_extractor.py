import io
import logging
import docx
from docx.document import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph

from .base import ExtractedPage

logger = logging.getLogger(__name__)

class DocxExtractor:
    """Extractor for DOCX files using python-docx.
    
    Extracts text from paragraphs, table cells, and headers separately.
    Preserves heading hierarchy in metadata.
    """
    
    async def extract(self, file_path_or_bytes: str | bytes, **kwargs) -> list[ExtractedPage]:
        pages: list[ExtractedPage] = []
        
        if isinstance(file_path_or_bytes, bytes):
            doc_file = io.BytesIO(file_path_or_bytes)
        else:
            doc_file = file_path_or_bytes
            
        try:
            doc = docx.Document(doc_file)
        except Exception as e:
            logger.error(f"Failed to load DOCX: {e}")
            return pages

        # Track heading hierarchy
        current_headings = {"h1": None, "h2": None, "h3": None, "h4": None, "h5": None, "h6": None}
        current_section = None
        
        # We process paragraphs and tables in document order
        # doc.element.body.inner_content contains both CT_P and CT_Tbl in order
        for block in doc.element.body:
            if isinstance(block, CT_P):
                p = Paragraph(block, doc)
                text = p.text.strip()
                if not text:
                    continue
                    
                style_name = p.style.name.lower()
                
                # Check for headings
                if style_name.startswith('heading'):
                    try:
                        level = int(style_name.replace('heading ', ''))
                        h_key = f"h{level}"
                        current_headings[h_key] = text
                        # Reset child headings
                        for l in range(level + 1, 7):
                            current_headings[f"h{l}"] = None
                        
                        current_section = text
                    except ValueError:
                        pass
                
                # Build metadata with hierarchy
                metadata = {}
                for k, v in current_headings.items():
                    if v is not None:
                        metadata[k] = v
                if current_section:
                    metadata["section"] = current_section
                    
                # We yield each paragraph as a "page" (chunk context) or combined
                # Here we map directly to an ExtractedPage to keep it simple,
                # the chunker can stitch them later.
                pages.append(
                    ExtractedPage(
                        page_number=1,
                        content=text,
                        content_type="text",
                        metadata=metadata
                    )
                )
                
            elif isinstance(block, CT_Tbl):
                table = Table(block, doc)
                md_table = self._table_to_markdown(table)
                
                metadata = {}
                for k, v in current_headings.items():
                    if v is not None:
                        metadata[k] = v
                if current_section:
                    metadata["section"] = current_section
                    
                if md_table:
                    pages.append(
                        ExtractedPage(
                            page_number=1,
                            content=md_table,
                            content_type="table",
                            metadata=metadata
                        )
                    )
                    
        return pages

    def _table_to_markdown(self, table: Table) -> str:
        """Convert python-docx Table to markdown."""
        if not table.rows:
            return ""
            
        data = []
        for row in table.rows:
            row_data = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            data.append(row_data)
            
        if not data:
            return ""
            
        header = data[0]
        rows = data[1:]
        
        md_lines = []
        md_lines.append("| " + " | ".join(header) + " |")
        md_lines.append("|" + "|".join(["---" for _ in header]) + "|")
        for row in rows:
            md_lines.append("| " + " | ".join(row) + " |")
            
        return "\n".join(md_lines)
