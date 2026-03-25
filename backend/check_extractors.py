import asyncio
import io
import pandas as pd
from fpdf import FPDF

from pipelines.ingestion.extractors import PDFExtractor, CSVExtractor

async def main():
    print("Testing PDF Extractor...")
    # Create simple PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    long_text = "Hello, World! This is a test PDF for NeuroFlow. " * 5
    pdf.cell(200, 10, txt=long_text, ln=1, align="C")
    
    # Save to bytes
    pdf_bytes = pdf.output(dest="S").encode("latin1")
    
    pdf_ext = PDFExtractor()
    pages = await pdf_ext.extract(pdf_bytes)
    print(f"PDF Pages extracted: {len(pages)}")
    for p in pages:
        print(f"Page {p.page_number} ({p.content_type}): {p.content[:50]}...")
        
    print("\nTesting CSV Extractor...")
    # Create small CSV
    df = pd.DataFrame({"A": [1,2,3], "B": ["x", "y", "z"]})
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    csv_ext = CSVExtractor()
    pages = await csv_ext.extract(csv_bytes)
    print(f"CSV Pages extracted: {len(pages)}")
    for p in pages:
        print(f"Page {p.page_number} ({p.content_type}):\n{p.content[:100]}...")

if __name__ == "__main__":
    asyncio.run(main())
