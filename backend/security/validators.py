import re

import bleach

try:
    import magic

    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False
from fastapi import HTTPException, UploadFile

# Private IP ranges for SSRF protection
PRIVATE_IP_REGEX = re.compile(r"^(10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.|127\.|localhost)")


def sanitize_text(text: str) -> str:
    """
    Strip HTML from text inputs using bleach.
    """
    return bleach.clean(text, tags=[], strip=True)


def validate_query(text: str, max_length: int = 5000) -> str:
    """
    Validate and sanitize query text.
    """
    sanitized = sanitize_text(text)
    if len(sanitized) > max_length:
        raise HTTPException(
            status_code=400, detail=f"Query too long. Max length is {max_length} characters."
        )
    return sanitized


def validate_pipeline_name(name: str, max_length: int = 100) -> str:
    """
    Validate and sanitize pipeline name.
    """
    sanitized = sanitize_text(name)
    if len(sanitized) > max_length:
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline name too long. Max length is {max_length} characters.",
        )
    return sanitized


def validate_url(url: str) -> None:
    """
    Validate URL: ^https?:// and block private IP ranges/localhost.
    """
    if not re.match(r"^https?://", url):
        raise HTTPException(
            status_code=400, detail="Invalid URL protocol. Only http and https are allowed."
        )

    # Simple check for private IPs in the hostname
    hostname: str = url.split("//")[-1].split("/")[0].split(":")[0]
    if PRIVATE_IP_REGEX.match(hostname):
        raise HTTPException(
            status_code=400,
            detail="Access to private IP ranges and localhost is forbidden (SSRF protection).",
        )


async def validate_file(file: UploadFile) -> None:
    """
    Check MIME type and magic bytes to ensure file is legitimate.
    """
    # 1. Check MIME type from headers
    allowed_types: list[str] = [
        "application/pdf",
        "text/plain",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/csv",
    ]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    # 2. Check Magic bytes
    if HAS_MAGIC:
        try:
            content: bytes = await file.read(2048)
            file_type: str = magic.from_buffer(content, mime=True)
            await file.seek(0)  # Reset file pointer

            if file_type not in allowed_types:
                # Simple text/plain fallback, but be strict for PDF
                if "pdf" in file.filename.lower() and file_type != "application/pdf":
                    raise HTTPException(
                        status_code=400, detail="File signature does not match PDF extension."
                    )
                if file_type == "application/x-executable" or file_type == "application/x-dosexec":
                    raise HTTPException(
                        status_code=400, detail="Executable files are strictly forbidden."
                    )
        except Exception:
            # Fallback to simple check if magic fails at runtime
            if "pdf" in file.filename.lower() and file.content_type != "application/pdf":
                raise HTTPException(
                    status_code=400, detail="MIME type does not match PDF extension."
                )
    else:
        # Fallback if magic is not installed
        if "pdf" in file.filename.lower() and file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="MIME type does not match PDF extension.")
