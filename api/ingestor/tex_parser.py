"""
LaTeX parser for direct document ingestion.

Parses .tex files into the same structured dict as md_parser.parse_markdown(),
using regex only (no pylatexenc required).
"""

import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_file(path: str) -> str:
    """Read a file trying UTF-8 first, then latin-1."""
    p = Path(path)
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        try:
            return p.read_text(encoding="latin-1", errors="replace")
        except Exception as exc:
            logger.warning(f"Could not read {path}: {exc}")
            return ""


def _extract_braced(text: str, start: int) -> str:
    """
    Extract the content of the first top-level {...} group starting at or
    after *start*.  Handles nested braces.
    Returns the content (without outer braces) or '' on failure.
    """
    depth = 0
    buf: list = []
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "{":
            if depth > 0:
                buf.append(ch)
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return "".join(buf)
            buf.append(ch)
        elif depth > 0:
            buf.append(ch)
        i += 1
    return "".join(buf)


def _strip_commands(text: str) -> str:
    r"""
    Remove LaTeX markup from *text*, preserving readable content.

    Rules applied (in order):
      1. Remove comments  %...
      2. Unwrap \textbf{...}, \textit{...}, \emph{...}, etc.
      3. Remove unknown \command{...} but keep the braced content
      4. Remove bare \command (no braces)
      5. Collapse whitespace
    """
    # 1. Strip LaTeX comments
    text = re.sub(r"(?m)%.*$", "", text)

    # 2. Unwrap well-known formatting commands (keep inner text)
    formatting = r"\\(?:textbf|textit|texttt|emph|underline|textsc|textrm|textsf|textsl|mbox|hbox|vbox|text|mathrm|mathbf|mathit|mathsf|mathtt|mathbb|mathcal|mathfrak)\{([^{}]*)\}"
    for _ in range(5):  # multiple passes for nesting
        text = re.sub(formatting, r"\1", text)

    # 3. Remove \command{content} → keep content  (handles remaining commands)
    for _ in range(5):
        text = re.sub(r"\\[a-zA-Z@]+\{([^{}]*)\}", r"\1", text)

    # 4. Remove bare \command[...] or \command
    text = re.sub(r"\\[a-zA-Z@]+\*?(?:\[[^\]]*\])*\s*", "", text)

    # 5. Remove stray braces
    text = text.replace("{", "").replace("}", "")

    # 6. Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _inline_includes(text: str, base_dir: str, depth: int = 0) -> str:
    """
    Recursively inline \\input{file} and \\include{file} references.
    Prevents infinite recursion with a depth limit of 5.
    """
    if depth > 5:
        return text

    def replacer(m: re.Match) -> str:
        ref = m.group(1).strip()
        if not ref.endswith(".tex"):
            ref += ".tex"
        sub_path = Path(base_dir) / ref
        if sub_path.exists():
            sub_text = _read_file(str(sub_path))
            return _inline_includes(sub_text, str(sub_path.parent), depth + 1)
        # Try just the filename in the base_dir (handles paths like ../other/file.tex)
        sub_path2 = Path(base_dir) / Path(ref).name
        if sub_path2.exists():
            sub_text = _read_file(str(sub_path2))
            return _inline_includes(sub_text, str(sub_path2.parent), depth + 1)
        logger.debug(f"Could not resolve \\input/\\include: {ref}")
        return ""

    return re.sub(r"\\(?:input|include)\{([^}]+)\}", replacer, text)


def _classify_section(heading: str) -> str:
    """Map a LaTeX section name to a checkpoint category."""
    h = heading.lower()
    if "abstract" in h:
        return "abstract"
    if any(
        k in h
        for k in (
            "introduction",
            "background",
            "related work",
            "related",
            "motivation",
            "prior work",
        )
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
            "design",
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
            "ablation",
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
# Environment extractors
# ---------------------------------------------------------------------------


def _extract_env(text: str, env_name: str) -> list:
    """Extract all contents of \\begin{env_name}...\\end{env_name}."""
    pattern = re.compile(
        r"\\begin\{"
        + re.escape(env_name)
        + r"\}(.*?)\\end\{"
        + re.escape(env_name)
        + r"\}",
        re.DOTALL | re.IGNORECASE,
    )
    return [m.group(1) for m in pattern.finditer(text)]


def _extract_command_arg(text: str, cmd: str) -> Optional[str]:
    """Extract first argument of \\cmd{...}."""
    m = re.search(r"\\" + re.escape(cmd) + r"\s*\{", text)
    if not m:
        return None
    return _extract_braced(text, m.end() - 1)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_latex(path: str) -> dict:
    """
    Parse a LaTeX file into structured content.

    Returns the same dict format as md_parser.parse_markdown():
        title, abstract, authors, sections, figures, tables, equations
    """
    base_dir = str(Path(path).parent)
    raw = _read_file(path)

    # Inline \\input / \\include sub-files
    raw = _inline_includes(raw, base_dir)

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
    # 1. Title                                                            #
    # ------------------------------------------------------------------ #
    title_raw = _extract_command_arg(raw, "title")
    if title_raw:
        result["title"] = _strip_commands(title_raw).strip()

    # ------------------------------------------------------------------ #
    # 2. Authors                                                          #
    # ------------------------------------------------------------------ #
    author_raw = _extract_command_arg(raw, "author")
    if author_raw:
        # Flatten multiple authors separated by \and or \\
        author_text = re.sub(r"\\and\b", ", ", author_raw)
        author_text = re.sub(r"\\\\", " ", author_text)
        result["authors"] = _strip_commands(author_text).strip()

    # ------------------------------------------------------------------ #
    # 3. Abstract                                                         #
    # ------------------------------------------------------------------ #
    abstracts = _extract_env(raw, "abstract")
    if abstracts:
        result["abstract"] = _strip_commands(abstracts[0]).strip()

    # ------------------------------------------------------------------ #
    # 4. Sections                                                         #
    # ------------------------------------------------------------------ #
    # Match \section, \subsection, \subsubsection (with optional *)
    _sec_re = re.compile(
        r"\\(section|subsection|subsubsection)\*?\s*\{([^}]*)\}", re.IGNORECASE
    )
    sec_matches = list(_sec_re.finditer(raw))

    _level_map = {"section": 1, "subsection": 2, "subsubsection": 3}

    for idx, m in enumerate(sec_matches):
        cmd = m.group(1).lower()
        heading = _strip_commands(m.group(2)).strip()
        level = _level_map.get(cmd, 1)

        # Extract section body: text until next section heading
        body_start = m.end()
        body_end = (
            sec_matches[idx + 1].start() if idx + 1 < len(sec_matches) else len(raw)
        )
        body_raw = raw[body_start:body_end]

        # Strip environments that are extracted separately
        body_clean = re.sub(
            r"\\begin\{(?:figure|table|tabular|equation|align|align\*|eqnarray|gather|gather\*)\}.*?\\end\{(?:figure|table|tabular|equation|align|align\*|eqnarray|gather|gather\*)\}",
            "",
            body_raw,
            flags=re.DOTALL,
        )
        text = _strip_commands(body_clean).strip()

        category = _classify_section(heading)

        result["sections"].append(
            {
                "heading": heading,
                "level": level,
                "text": text,
                "category": category,
            }
        )

        if category == "abstract" and not result["abstract"]:
            result["abstract"] = text

    # ------------------------------------------------------------------ #
    # 5. Figures                                                          #
    # ------------------------------------------------------------------ #
    # From \begin{figure}...\end{figure} environments
    for fig_env in _extract_env(raw, "figure"):
        caption = ""
        cap_m = re.search(r"\\caption\{", fig_env)
        if cap_m:
            caption = _strip_commands(_extract_braced(fig_env, cap_m.end() - 1))

        # Find \includegraphics[...]{file}
        for ig_m in re.finditer(
            r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", fig_env
        ):
            result["figures"].append(
                {
                    "caption": caption.strip(),
                    "path": ig_m.group(1).strip(),
                }
            )

    # Also pick up bare \includegraphics outside figure environments
    _fig_env_re = re.compile(
        r"\\begin\{figure\}.*?\\end\{figure\}", re.DOTALL | re.IGNORECASE
    )
    raw_no_figs = _fig_env_re.sub("", raw)
    for ig_m in re.finditer(
        r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", raw_no_figs
    ):
        result["figures"].append({"caption": "", "path": ig_m.group(1).strip()})

    # ------------------------------------------------------------------ #
    # 6. Tables                                                           #
    # ------------------------------------------------------------------ #
    for tab_env in _extract_env(raw, "tabular"):
        result["tables"].append(tab_env.strip())

    # Also grab whole table environments (for caption context)
    for tbl_env in _extract_env(raw, "table"):
        # Only if it doesn't contain a tabular (already captured above)
        if r"\begin{tabular}" not in tbl_env:
            cap_m = re.search(r"\\caption\{", tbl_env)
            if cap_m:
                cap = _strip_commands(_extract_braced(tbl_env, cap_m.end() - 1))
                result["tables"].append(f"[Table: {cap.strip()}]")

    # ------------------------------------------------------------------ #
    # 7. Equations                                                        #
    # ------------------------------------------------------------------ #
    # Named environments
    for env in (
        "equation",
        "equation*",
        "align",
        "align*",
        "eqnarray",
        "gather",
        "gather*",
        "multline",
        "multline*",
    ):
        for content in _extract_env(raw, env):
            eq = content.strip()
            if eq:
                result["equations"].append(eq)

    # Inline $...$
    for m in re.finditer(r"(?<!\$)\$(?!\$)([^$\n]{2,}?)(?<!\$)\$(?!\$)", raw):
        eq = m.group(1).strip()
        if eq:
            result["equations"].append(eq)

    # $$...$$ display math
    for m in re.finditer(r"\$\$(.+?)\$\$", raw, re.DOTALL):
        eq = m.group(1).strip()
        if eq:
            result["equations"].append(eq)

    # Deduplicate equations (preserve order)
    seen: set = set()
    unique_eqs = []
    for eq in result["equations"]:
        if eq not in seen:
            seen.add(eq)
            unique_eqs.append(eq)
    result["equations"] = unique_eqs

    logger.debug(
        "parse_latex: title=%r sections=%d figures=%d tables=%d equations=%d",
        result["title"],
        len(result["sections"]),
        len(result["figures"]),
        len(result["tables"]),
        len(result["equations"]),
    )
    return result
