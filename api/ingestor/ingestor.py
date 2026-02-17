"""
Direct document ingestor for Paper2Slides.

Parses .md / .tex / .zip files directly into checkpoint_rag.json format,
bypassing MinerU entirely.  The pipeline then starts at the "summary" stage.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(query: str, answer: str) -> dict:
    return {
        "query": query,
        "answer": answer,
        "mode": "direct_parse",
        "success": True,
    }


def _collect_category_text(sections: list, category: str) -> str:
    """Concatenate text from all sections belonging to *category*."""
    parts = [
        s["text"] for s in sections if s.get("category") == category and s.get("text")
    ]
    return "\n\n".join(parts).strip()


def _summarise_figures(figures: list) -> str:
    if not figures:
        return "No figures detected."
    lines = []
    for i, fig in enumerate(figures, 1):
        cap = fig.get("caption", "").strip()
        path = fig.get("path", "").strip()
        if cap and path:
            lines.append(f"Figure {i}: {cap} (file: {path})")
        elif cap:
            lines.append(f"Figure {i}: {cap}")
        elif path:
            lines.append(f"Figure {i}: {path}")
        else:
            lines.append(f"Figure {i}: (no description)")
    return "\n".join(lines)


def _summarise_tables(tables: list) -> str:
    if not tables:
        return "No tables detected."
    lines = []
    for i, tbl in enumerate(tables, 1):
        preview = tbl.strip()[:200].replace("\n", " ")
        lines.append(f"Table {i}: {preview}")
    return "\n".join(lines)


def _summarise_equations(equations: list) -> str:
    if not equations:
        return "No equations detected."
    lines = []
    for i, eq in enumerate(equations[:30], 1):  # cap at 30 to avoid bloat
        lines.append(f"Eq. {i}: {eq.strip()[:120]}")
    if len(equations) > 30:
        lines.append(f"... and {len(equations) - 30} more equations.")
    return "\n".join(lines)


def _build_export_markdown(parsed: dict, file_path: str) -> str:
    """Build a clean Markdown export from the parsed document."""
    lines = []

    title = parsed.get("title", "") or Path(file_path).stem
    lines.append(f"# {title}\n")

    authors = parsed.get("authors", "")
    if authors:
        lines.append(f"**Authors:** {authors}\n")

    abstract = parsed.get("abstract", "")
    if abstract:
        lines.append("## Abstract\n")
        lines.append(abstract + "\n")

    for sec in parsed.get("sections", []):
        heading = sec.get("heading", "Section")
        level = sec.get("level", 2)
        text = sec.get("text", "")
        hashes = "#" * min(max(level, 2), 6)
        lines.append(f"{hashes} {heading}\n")
        if text:
            lines.append(text + "\n")

    figs = parsed.get("figures", [])
    if figs:
        lines.append("## Figures\n")
        lines.append(_summarise_figures(figs) + "\n")

    tbls = parsed.get("tables", [])
    if tbls:
        lines.append("## Tables\n")
        for i, t in enumerate(tbls, 1):
            lines.append(f"### Table {i}\n")
            lines.append(t + "\n")

    eqs = parsed.get("equations", [])
    if eqs:
        lines.append("## Equations\n")
        lines.append(_summarise_equations(eqs) + "\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ingest_document(file_path: str, config: dict, base_dir: str) -> dict:
    """
    Parse a .md, .tex, or .zip file directly into checkpoint_rag.json.

    Writes:
      - {base_dir}/fast/rag_output/export.md   (clean markdown export)
      - {base_dir}/fast/checkpoint_rag.json     (RAG checkpoint)

    Args:
        file_path: Path to the source document.
        config:    Pipeline config dict (used for content_type / input_path).
        base_dir:  Base directory = OUTPUT_DIR / project_name / content_type.

    Returns:
        The rag_data dict that was written to checkpoint_rag.json.

    Raises:
        ValueError: Unsupported file extension.
    """
    fp = Path(file_path)
    ext = fp.suffix.lower()
    content_type = config.get("content_type", "paper")

    logger.info(f"ingest_document: {fp.name} (ext={ext}, content_type={content_type})")

    # ------------------------------------------------------------------ #
    # 1. Parse source document into structured dict                       #
    # ------------------------------------------------------------------ #
    parsed: dict

    if ext in (".md", ".markdown"):
        from .md_parser import parse_markdown

        parsed = parse_markdown(file_path)

    elif ext == ".tex":
        from .tex_parser import parse_latex

        parsed = parse_latex(file_path)

    elif ext == ".zip":
        from .zip_handler import extract_and_find_main

        extract_dir = str(Path(base_dir) / "fast" / "zip_extract")
        main_tex = extract_and_find_main(file_path, extract_dir)
        from .tex_parser import parse_latex

        parsed = parse_latex(main_tex)

    else:
        raise ValueError(
            f"ingest_document: unsupported file extension '{ext}' "
            f"(supported: .md, .markdown, .tex, .zip)"
        )

    # ------------------------------------------------------------------ #
    # 2. Write clean markdown export                                      #
    # ------------------------------------------------------------------ #
    fast_dir = Path(base_dir) / "fast"
    rag_output_dir = fast_dir / "rag_output"
    rag_output_dir.mkdir(parents=True, exist_ok=True)

    export_md_path = rag_output_dir / "export.md"
    export_md_content = _build_export_markdown(parsed, file_path)
    export_md_path.write_text(export_md_content, encoding="utf-8")
    logger.info(f"  Export MD: {export_md_path}")

    # ------------------------------------------------------------------ #
    # 3. Build rag_results dict                                           #
    # ------------------------------------------------------------------ #
    title = parsed.get("title", "") or fp.stem
    authors = parsed.get("authors", "") or "Unknown"
    abstract = parsed.get("abstract", "") or "Not provided."
    sections = parsed.get("sections", [])

    # Collect text by category
    motivation_text = _collect_category_text(sections, "motivation")
    solution_text = _collect_category_text(sections, "solution")
    results_text = _collect_category_text(sections, "results")
    contributions_text = _collect_category_text(sections, "contributions")
    paper_info_text = _collect_category_text(sections, "paper_info")

    # Build paper_info answer
    paper_info_answer = f"Title: {title}\nAuthors: {authors}\nAbstract: {abstract}"
    if paper_info_text:
        paper_info_answer += f"\n\nAdditional content:\n{paper_info_text}"

    rag_results = {
        "paper_info": [
            _make_result(
                "What is this document about?",
                paper_info_answer,
            )
        ],
        "motivation": [
            _make_result(
                "What is the problem/motivation?",
                motivation_text or "Not explicitly stated.",
            )
        ],
        "solution": [
            _make_result(
                "What is the proposed solution/method?",
                solution_text or "Not explicitly stated.",
            )
        ],
        "results": [
            _make_result(
                "What are the results/findings?",
                results_text or "Not explicitly stated.",
            )
        ],
        "contributions": [
            _make_result(
                "What are the contributions/conclusions?",
                contributions_text or "Not explicitly stated.",
            )
        ],
        "figures": [
            _make_result(
                "What figures are in the document?",
                _summarise_figures(parsed.get("figures", [])),
            )
        ],
        "tables": [
            _make_result(
                "What tables are in the document?",
                _summarise_tables(parsed.get("tables", [])),
            )
        ],
        "equations": [
            _make_result(
                "What equations are in the document?",
                _summarise_equations(parsed.get("equations", [])),
            )
        ],
    }

    # ------------------------------------------------------------------ #
    # 4. Assemble and write checkpoint_rag.json                           #
    # ------------------------------------------------------------------ #
    rag_data = {
        "rag_results": rag_results,
        "markdown_paths": [str(export_md_path)],
        "input_path": file_path,
        "content_type": content_type,
        "mode": "fast",
    }

    checkpoint_path = fast_dir / "checkpoint_rag.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(rag_data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info(f"  Checkpoint: {checkpoint_path}")

    return rag_data
