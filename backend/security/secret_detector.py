import re
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

SECRET_PATTERNS = {
    "AWS Access Key": r"AKIA[0-9A-Z]{16}",
    "Generic API Key": r"['\"]?(?:api|secret|token|key|password)['\"]?\s*[:=]\s*['\"][A-Za-z0-9/+]{20,}['\"]",
    "Private Key PEM": r"-----BEGIN (?:RSA|OPENSSH|DSA|EC|PGP) PRIVATE KEY-----",
    "JWT Token": r"(?:^|(?<=\s))ey[A-Za-z0-9-_]+\.ey[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+"
}

def scan_and_redact_secrets(content: str, document_id: str = "unknown") -> str:
    """
    Scan for secrets and replace with [REDACTED].
    """
    redacted_content = content
    for pattern_type, pattern in SECRET_PATTERNS.items():
        matches = re.findall(pattern, redacted_content)
        if matches:
            logger.info(f"Secret detected and redacted: {pattern_type} in {document_id}")
            # The prompt requires logging specifically: {"event": "secret_redacted", "document_id": ..., "pattern_type": ...}
            logger.info(json.dumps({"event": "secret_redacted", "document_id": document_id, "pattern_type": pattern_type}))
            redacted_content = re.sub(pattern, "[REDACTED]", redacted_content)
    
    return redacted_content
