import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)


class DocumentSandbox:
    """
    Sandboxes document processing using Docker.
    Runs a container with no networking and limited memory to extract text.
    """

    IMAGE_NAME = "python:3.9-slim"

    @classmethod
    def extract_text(cls, file_content: bytes, filename: str) -> str:
        """
        Extract text from file content using a sandboxed Docker container.
        """
        # Create a temporary directory to share with the container
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_file_path = os.path.join(tmpdir, "input_file")
            with open(temp_file_path, "wb") as f:
                f.write(file_content)

            # Minimal script to "extract" text.
            # In a real scenario, this would use pdfminer or similar inside the container.
            # For this task, we'll simulate the extraction process inside the sandbox.
            extraction_script = """
import sys
import os

# Simulate processing
filename = os.environ.get('FILENAME', 'unknown')
try:
    with open('/mnt/input_file', 'rb') as f:
        content = f.read()
        # Mock extraction logic
        if filename.endswith('.pdf'):
            # In a real app: text = extract_pdf(content)
            print(f"Extracted PDF content from {filename}")
        else:
            print(content.decode('utf-8', errors='ignore'))
except Exception as e:
    print(f"Extraction error: {e}", file=sys.stderr)
    sys.exit(1)
"""
            script_path = os.path.join(tmpdir, "extract.py")
            with open(script_path, "w") as f:
                f.write(extraction_script)

            # Docker command
            # --network none: no internet
            # --memory 256m: resource limit
            # --rm: clean up
            # -v: mount the temp dir
            cmd = [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--memory",
                "256m",
                "-v",
                f"{os.path.abspath(tmpdir)}:/mnt:ro",
                "-e",
                f"FILENAME={filename}",
                cls.IMAGE_NAME,
                "python",
                "/mnt/extract.py",
            ]

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,  # Safety timeout
                )

                if result.returncode != 0:
                    logger.error(f"Sandbox extraction failed: {result.stderr}")
                    return f"Error: Sandbox failed to process {filename}"

                return result.stdout.strip()

            except subprocess.TimeoutExpired:
                logger.error(f"Sandbox extraction timed out for {filename}")
                return f"Error: Timeout processing {filename}"
            except Exception as e:
                logger.error(f"Error running sandbox: {e}")
                return "Error: System error during sandboxing"


def process_document_sandboxed(content: bytes, filename: str) -> str:
    """Helper function to run the sandbox."""
    sandbox: DocumentSandbox = DocumentSandbox()
    return sandbox.extract_text(content, filename)
