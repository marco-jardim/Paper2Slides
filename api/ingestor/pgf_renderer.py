"""
PGF renderer – compiles a PGF file to PNG using pdflatex standalone.

Optional: requires pdflatex on PATH (or at the fallback Windows path).
Returns None gracefully when unavailable.
"""

import shutil
import subprocess
import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PDFLATEX_FALLBACK = r"C:\texlive\2024\bin\windows\pdflatex.exe"
_PDFLATEX = (
    "pdflatex"
    if shutil.which("pdflatex")
    else (_PDFLATEX_FALLBACK if Path(_PDFLATEX_FALLBACK).exists() else None)
)

_STANDALONE_TEX = r"""\documentclass[border=2pt]{{standalone}}
\usepackage{{pgf}}
\begin{{document}}
\input{{{pgf_path}}}
\end{{document}}
"""


def render_pgf_to_png(pgf_path: str, output_dir: str) -> Optional[str]:
    """
    Compile a PGF file to PNG via pdflatex standalone + pdf2image / PIL.

    Args:
        pgf_path:   Absolute path to the .pgf file.
        output_dir: Directory where the PNG (or PDF fallback) is written.

    Returns:
        Path to the generated PNG (or PDF if conversion unavailable),
        or None on any failure.
    """
    if _PDFLATEX is None:
        logger.warning("pdflatex not found; skipping PGF rendering.")
        return None

    pgf_abs = Path(pgf_path).resolve()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = pgf_abs.stem

    with tempfile.TemporaryDirectory() as tmp:
        tex_file = Path(tmp) / f"{stem}.tex"
        # Use forward slashes for pdflatex compatibility
        pgf_posix = str(pgf_abs).replace("\\", "/")
        tex_file.write_text(
            _STANDALONE_TEX.format(pgf_path=pgf_posix), encoding="utf-8"
        )

        cmd = [
            str(_PDFLATEX),
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={tmp}",
            str(tex_file),
        ]
        try:
            result = subprocess.run(
                cmd,
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning(f"pdflatex failed for {pgf_path}: {exc}")
            return None

        if result.returncode != 0:
            last_lines = "\n".join(result.stdout.splitlines()[-10:])
            logger.warning(f"pdflatex non-zero exit for {pgf_path}:\n{last_lines}")
            return None

        pdf_tmp = Path(tmp) / f"{stem}.pdf"
        if not pdf_tmp.exists():
            logger.warning(f"PDF not generated for {pgf_path}")
            return None

        # Copy PDF to output first (fallback return value)
        pdf_out = out_dir / f"{stem}.pdf"
        import shutil as _shutil

        _shutil.copy2(str(pdf_tmp), str(pdf_out))

        # Attempt PDF → PNG conversion
        png_out = out_dir / f"{stem}.png"
        try:
            from pdf2image import convert_from_path  # type: ignore[import]

            images = convert_from_path(str(pdf_out), dpi=150, first_page=1, last_page=1)
            if images:
                images[0].save(str(png_out), "PNG")
                logger.info(f"PGF rendered → {png_out.name}")
                return str(png_out)
        except Exception:
            pass

        # Fallback: try PIL / Pillow directly on PDF
        try:
            from PIL import Image  # type: ignore[import]

            img = Image.open(str(pdf_out))
            img.save(str(png_out), "PNG")
            logger.info(f"PGF rendered (PIL) → {png_out.name}")
            return str(png_out)
        except Exception:
            pass

        # Return PDF path as last resort
        logger.info(f"PGF compiled to PDF (no PNG converter) → {pdf_out.name}")
        return str(pdf_out)
