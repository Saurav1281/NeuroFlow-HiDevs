import logging
import urllib.robotparser
from urllib.parse import urlparse
import httpx
import trafilatura
from typing import List

from .base import ExtractedPage

logger = logging.getLogger(__name__)

class URLExtractor:
    """Extractor for URLs.
    
    Validates robots.txt, fetches the page asynchronously via httpx,
    and extracts content and metadata using trafilatura.
    """
    
    async def extract(self, url: str, **kwargs) -> list[ExtractedPage]:
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Check robots.txt
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{base_url}/robots.txt")
        try:
            rp.read()
            if not rp.can_fetch("*", url):
                logger.warning(f"robots.txt prevents fetching {url}")
                return []
        except Exception as e:
            logger.warning(f"Failed to read robots.txt for {base_url}: {e}")
            # If robots.txt fetch fails, standard practice may be to proceed or block.
            # We'll proceed with caution.
            pass
            
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                html_content = response.text
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch URL {url}: {e}")
            return []
            
        # Extract main content and metadata using trafilatura
        extracted_result = trafilatura.extract(
            html_content,
            include_tables=True,
            output_format="json"  # Built-in json dict returns both content and metadata
        )
        
        if not extracted_result:
            logger.warning(f"Trafilatura returned empty result for {url}")
            return []
            
        import json
        data = json.loads(extracted_result)
        
        content = data.get("text", "")
        # The json output splits content into lines. Trafilatura combines them in text?
        # In trafilatura, output_format="json" returns a JSON string, which we parse.
        
        metadata = {
            "source_url": url,
            "title": data.get("title", ""),
            "author": data.get("author", ""),
            "canonical_url": data.get("source", ""),
            "publish_date": data.get("date", ""),
        }
        
        return [
            ExtractedPage(
                page_number=1,
                content=content.strip(),
                content_type="text",
                metadata=metadata
            )
        ]
