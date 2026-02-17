"""
ZIP handler for direct document ingestion.

Extracts a ZIP archive and identifies the main .tex file using a
scoring heuristic (same logic previously in preprocessor.detect_main_tex).
"""

import re
import zipfile
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def extract_and_find_main(zip_path: str, extract_dir: str) -> str:
    """
    Extract a ZIP archive and return the path to the main .tex file.

    Scoring heuristic per .tex file:
        +100  contains \\documentclass
        +50   contains \\begin{document}
        -10   for each time it is \\input{} / \\include{}'d by another file
              (i.e. it is a sub-file, not the root)

    Args:
        zip_path:    Path to the .zip file.
        extract_dir: Destination directory (created if absent).

    Returns:
        Absolute path of the highest-scoring .tex file.

    Raises:
        ValueError: No .tex files found in the archive.
        RuntimeError: ZIP extraction failed.
    """
    extract_path = Path(extract_dir)
    extract_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"Extracting ZIP: {Path(zip_path).name} → {extract_path}")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(str(extract_path))
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"Bad ZIP file: {zip_path}") from exc

    tex_files = list(extract_path.rglob("*.tex"))
    if not tex_files:
        raise ValueError(f"No .tex files found in ZIP archive: {Path(zip_path).name}")

    # Read all file contents up-front
    contents: dict = {}
    for tf in tex_files:
        try:
            contents[str(tf)] = tf.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            logger.warning(f"Could not read {tf}: {exc}")
            contents[str(tf)] = ""

    # Count how many times each file is included by another
    inclusion_count: dict = {str(tf): 0 for tf in tex_files}
    include_re = re.compile(r"\\(?:input|include)\{([^}]+)\}")

    for reader_path, content in contents.items():
        for match in include_re.finditer(content):
            included = match.group(1).strip()
            if not included.endswith(".tex"):
                included += ".tex"
            included_name = Path(included).name
            for tf in tex_files:
                if str(tf) != reader_path and (
                    tf.name == included_name
                    or str(tf).replace("\\", "/").endswith(included.replace("\\", "/"))
                ):
                    inclusion_count[str(tf)] = inclusion_count.get(str(tf), 0) + 1

    # Score and rank
    scores: dict = {}
    for tex_path, content in contents.items():
        score = 0
        if r"\documentclass" in content:
            score += 100
        if r"\begin{document}" in content:
            score += 50
        score -= 10 * inclusion_count.get(tex_path, 0)
        scores[tex_path] = score

    best = max(scores, key=lambda k: scores[k])
    logger.info(f"Main .tex detected: {Path(best).name} (score={scores[best]})")
    return best
