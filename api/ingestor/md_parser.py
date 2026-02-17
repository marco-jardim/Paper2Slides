"""
Markdown parser for direct document ingestion.

Parses .md / .markdown files into a structured dict compatible with
checkpoint_rag.json without going through MinerU or PDF conversion.
"""

import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section category classifier
# ---------------------------------------------------------------------------


def _classify_section(heading: str) -> str:
    """Map a section heading to one of the checkpoint categories."""
    h = heading.lower()
    if "abstract" in h:
        return "abstract"
    if any(
        k in h
        for k in ("introduction", "background", "related work", "related", "prior")
    ):
        return "motivation"
    if any(
        k in h
        for k in (
            "method",
            "approach",
            "model",
            "architecture",
            "system",
            "proposed",
            "framework",
        )
    ):
        return "solution"
    if any(
        k in h
        for k in (
            "result",
            "experiment",
            "evaluation",
            "performance",
            "benchmark",
            "analysis",
        )
    ):
        return "results"
    if any(
        k in h
        for k in ("conclusion", "contribution", "summary", "discussion", "future")
    ):
        return "contributions"
    return "paper_info"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_markdown(path: str) -> dict:
    """
    Parse a Markdown file into structured content.

    Returns a dict with keys:
        title       – str, document title
        abstract    – str, abstract text (may be empty)
        authors     – str, author line (may be empty)
        sections    – list of {heading, level, text, category}
        figures     – list of {caption, path}
        tables      – list of str (raw table text)
        equations   – list of str (math expressions)
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")

    result: dict = {
        "title": "",
        "abstract": "",
        "authors": "",
        "sections": [],
        "figures": [],
        "tables": [],
        "equations": [],
    }

    # ------------------------------------------------------------------ #
    # 1. YAML / TOML frontmatter                                         #
    # ------------------------------------------------------------------ #
    frontmatter: dict = {}
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                frontmatter[k.strip().lower()] = v.strip()
        text = text[fm_match.end() :]

    if "title" in frontmatter:
        result["title"] = frontmatter["title"].strip("\"'")
    if "author" in frontmatter:
        result["authors"] = frontmatter["author"]
    if "authors" in frontmatter:
        result["authors"] = frontmatter["authors"]

    # ------------------------------------------------------------------ #
    # 2. Block equations  $$...$$                                         #
    # ------------------------------------------------------------------ #
    _block_eq_re = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
    for m in _block_eq_re.finditer(text):
        eq = m.group(1).strip()
        if eq:
            result["equations"].append(eq)
    # Replace block equations so inline scanner doesn't double-count
    text_no_block = _block_eq_re.sub("[EQUATION]", text)

    # ------------------------------------------------------------------ #
    # 3. Inline equations  $...$                                          #
    # ------------------------------------------------------------------ #
    _inline_eq_re = re.compile(r"(?<!\$)\$(?!\$)([^$\n]{2,}?)(?<!\$)\$(?!\$)")
    for m in _inline_eq_re.finditer(text_no_block):
        eq = m.group(1).strip()
        if eq:
            result["equations"].append(eq)

    # ------------------------------------------------------------------ #
    # 4. Figures  ![alt](path)                                            #
    # ------------------------------------------------------------------ #
    for m in re.finditer(r"!\[([^\]]*)\]\(([^)]*)\)", text):
        result["figures"].append(
            {"caption": m.group(1).strip(), "path": m.group(2).strip()}
        )

    # ------------------------------------------------------------------ #
    # 5. Tables (runs of lines containing |)                              #
    # ------------------------------------------------------------------ #
    table_buf: list = []
    for line in text.splitlines():
        stripped = line.strip()
        if "|" in stripped:
            table_buf.append(line)
        else:
            if table_buf:
                # Only keep if it looks like a real table (has separator row or ≥2 rows)
                raw = "\n".join(table_buf)
                if len(table_buf) >= 2 or re.search(r"\|[-:]+\|", raw):
                    result["tables"].append(raw)
                table_buf = []
    if table_buf:
        result["tables"].append("\n".join(table_buf))

    # ------------------------------------------------------------------ #
    # 6. Headings & sections                                              #
    # ------------------------------------------------------------------ #
    # Split document at heading boundaries.
    # re.split with 2 capturing groups returns:
    #   [pre, hashes, heading_text, body, hashes, heading_text, body, ...]
    _heading_re = re.compile(r"^(#{1,6})\s+(.+?)[ \t]*$", re.MULTILINE)
    parts = _heading_re.split(text)

    # parts[0] is preamble (before first heading)
    # Extract title from first H1 if not found in frontmatter
    for i in range(1, len(parts), 3):
        level_str = parts[i]  # e.g. '##'
        heading = parts[i + 1].strip()
        body = parts[i + 2].strip() if (i + 2) < len(parts) else ""

        level = len(level_str)

        # Title: first H1
        if level == 1 and not result["title"]:
            result["title"] = heading

        category = _classify_section(heading)

        result["sections"].append(
            {
                "heading": heading,
                "level": level,
                "text": body,
                "category": category,
            }
        )

        # Capture abstract
        if category == "abstract" and not result["abstract"]:
            result["abstract"] = body

    # ------------------------------------------------------------------ #
    # 7. Try to extract authors from preamble / first paragraph          #
    # ------------------------------------------------------------------ #
    if not result["authors"]:
        preamble = parts[0] if parts else ""
        # Look for lines that might be author lines (after the title line)
        lines = [ln.strip() for ln in preamble.splitlines() if ln.strip()]
        # Skip H1 title line if present
        non_heading = [ln for ln in lines if not ln.startswith("#")]
        if non_heading:
            # Use first non-heading line as potential author line
            candidate = non_heading[0]
            # Heuristic: likely authors if short and comma/and separated
            if len(candidate) < 200 and (
                "," in candidate
                or " and " in candidate.lower()
                or re.match(r"[A-Z][a-z]+", candidate)
            ):
                result["authors"] = candidate

    logger.debug(
        "parse_markdown: title=%r sections=%d figures=%d tables=%d equations=%d",
        result["title"],
        len(result["sections"]),
        len(result["figures"]),
        len(result["tables"]),
        len(result["equations"]),
    )
    return result
