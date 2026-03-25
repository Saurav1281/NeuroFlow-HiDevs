import io
import pandas as pd
from typing import List

from .base import ExtractedPage

class CSVExtractor:
    """Extractor for CSV files using pandas.
    
    Small CSVs (<1000 rows) are converted to markdown tables in blocks of 100 rows.
    Large CSVs (>=1000 rows) yield a statistical summary and sample rows.
    """
    
    async def extract(self, file_path_or_bytes: str | bytes, **kwargs) -> list[ExtractedPage]:
        pages: list[ExtractedPage] = []
        
        if isinstance(file_path_or_bytes, bytes):
            data = io.BytesIO(file_path_or_bytes)
        else:
            data = file_path_or_bytes
            
        try:
            df = pd.read_csv(data)
        except Exception as e:
            # Maybe return empty or a single page with error string
            return []
            
        row_count = len(df)
        
        if row_count < 1000:
            # Small CSV -> Markdown tables (100 row blocks)
            block_size = 100
            for start_idx in range(0, row_count, block_size):
                end_idx = min(start_idx + block_size, row_count)
                chunk_df = df.iloc[start_idx:end_idx]
                md_table = chunk_df.to_markdown(index=False)
                
                page_num = (start_idx // block_size) + 1
                pages.append(
                    ExtractedPage(
                        page_number=page_num,
                        content=md_table,
                        content_type="table",
                        metadata={"type": "small_csv", "rows_range": f"{start_idx}-{end_idx}"}
                    )
                )
        else:
            # Large CSV -> Statistical summary + sample rows
            summary_lines = [f"### Large CSV Summary ({row_count} rows, {len(df.columns)} columns)"]
            
            summary_lines.append("\n#### Column Names and Data Types:")
            for col in df.columns:
                summary_lines.append(f"- **{col}**: {df[col].dtype}")
                
            # Numeric stats
            numeric_cols = df.select_dtypes(include=['number'])
            if not numeric_cols.empty:
                summary_lines.append("\n#### Numeric Columns Summaries:")
                stats = numeric_cols.describe().T
                if 'mean' in stats.columns and 'min' in stats.columns and 'max' in stats.columns:
                    stats_filtered = stats[['min', 'max', 'mean']]
                    summary_lines.append(stats_filtered.to_markdown())
                    
            # Categorical stats
            cat_cols = df.select_dtypes(exclude=['number'])
            if not cat_cols.empty:
                summary_lines.append("\n#### Categorical Columns (Top 5 values):")
                for col in cat_cols.columns:
                    top_5 = df[col].value_counts().head(5)
                    summary_lines.append(f"**{col}**:")
                    for val, count in top_5.items():
                        summary_lines.append(f"  - {val}: {count}")
                        
            # Sample rows
            summary_lines.append("\n#### Sample Rows (First 5):")
            sample_df = df.head(5)
            summary_lines.append(sample_df.to_markdown(index=False))
            
            pages.append(
                ExtractedPage(
                    page_number=1,
                    content="\n".join(summary_lines),
                    content_type="text",
                    metadata={"type": "large_csv_summary"}
                )
            )
            
        return pages
