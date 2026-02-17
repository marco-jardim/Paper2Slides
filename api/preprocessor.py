"""
Backward-compatibility stub for api/preprocessor.py.

The preprocessing logic has been superseded by api/ingestor/ which parses
.md, .tex, and .zip files directly into checkpoint_rag.json without PDF
conversion.  This module is retained only so that any external references
do not immediately break at import time.

DO NOT add new functionality here – extend api/ingestor/ instead.
"""

from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def detect_file_type(path: str) -> str:
    """
    Detect file type based on extension.
    Returns one of: 'pdf', 'markdown', 'latex', 'zip'.
    Raises ValueError for unsupported extensions.
    """
    ext = Path(path).suffix.lower()
    _map = {
        ".pdf": "pdf",
        ".md": "markdown",
        ".markdown": "markdown",
        ".tex": "latex",
        ".zip": "zip",
    }
    if ext not in _map:
        raise ValueError(f"Unsupported file extension: '{ext}' (path={path})")
    return _map[ext]


def preprocess_to_pdf(file_path: str, session_dir: str) -> str:
    """
    DEPRECATED – PDF conversion is no longer performed for .md/.tex/.zip.

    Raises RuntimeError to make clear that callers should use the ingestor
    instead of attempting PDF conversion.
    """
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return file_path
    raise RuntimeError(
        f"preprocess_to_pdf is deprecated. "
        f"Use api/ingestor.ingest_document() for '{ext}' files."
    )
