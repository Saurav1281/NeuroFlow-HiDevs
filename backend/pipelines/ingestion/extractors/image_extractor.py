import io
import base64
import logging
from PIL import Image
import pytesseract

from .base import ExtractedPage
from providers.client import NeuroFlowClient
from providers.router import RoutingCriteria
from providers.base import ChatMessage

logger = logging.getLogger(__name__)

class ImageExtractor:
    """Extractor for images (JPEG, PNG, WEBP).
    
    Resizes image to max 1024px, extracts OCR text, and uses a Vision LLM to generate
    a description. Combined result is returned as an ExtractedPage.
    """
    
    async def extract(self, file_path_or_bytes: str | bytes, **kwargs) -> list[ExtractedPage]:
        if isinstance(file_path_or_bytes, bytes):
            img_bytes = file_path_or_bytes
        else:
            with open(file_path_or_bytes, "rb") as f:
                img_bytes = f.read()
                
        try:
            image = Image.open(io.BytesIO(img_bytes))
            # Convert to RGB if necessary
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
        except Exception as e:
            logger.error(f"Failed to open image: {e}")
            return []
            
        # Resize to max 1024px on longest side
        max_size = 1024
        if image.width > max_size or image.height > max_size:
            ratio = min(max_size / image.width, max_size / image.height)
            new_size = (int(image.width * ratio), int(image.height * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            
        # Run OCR
        ocr_text = ""
        try:
            ocr_text = pytesseract.image_to_string(image).strip()
        except Exception as e:
            logger.error(f"OCR failed on image: {e}")
            
        # Prepare for Vision LLM
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        b64_img = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        # We need the client to be initialized previously (e.g. by worker startup)
        client = NeuroFlowClient()
        description = ""
        
        try:
            # Multi-modal payload structure
            content = [
                {"type": "text", "text": "Please provide a detailed description of this image. Focus on visual details, context, and any structural information such as diagrams or charts."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
            ]
            
            messages = [ChatMessage(role="user", content=content)]
            criteria = RoutingCriteria(require_vision=True, task_type="rag_generation")
            
            result = await client.chat(messages, routing_criteria=criteria)
            description = result.content.strip()
        except Exception as e:
            logger.error(f"Vision LLM failed to describe image: {e}")
            description = "[Vision Model Unavailable or Failed]"
            
        # Combine descriptions
        combined_content = description
        if ocr_text:
            combined_content += f"\n\nText found in image:\n{ocr_text}"
            
        return [
            ExtractedPage(
                page_number=1,
                content=combined_content,
                content_type="image_description",
                metadata={"has_ocr": bool(ocr_text)}
            )
        ]
