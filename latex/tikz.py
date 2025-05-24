import tempfile
import subprocess
import io
import logging
from pathlib import Path
import discord
from .parser import sanitize_tikz_code

log = logging.getLogger("red.latex.tikz")

LATEX_TIKZ_TEMPLATE = r"""
\documentclass[border=2pt]{standalone}
\usepackage{tikz}
\usepackage[dvipsnames]{xcolor}
\usetikzlibrary{arrows.meta,positioning,calc}
\begin{document}
%s
\end{document}
"""


async def generate_tikz_image(tikz_code: str) -> discord.File | None:
    """Securely compile TikZ code to PNG and return as a Discord file."""
    sanitized_code = sanitize_tikz_code(tikz_code)
    if r"\begin{tikzpicture}" not in sanitized_code:
        log.warning("Input does not contain a TikZ environment.")
        return None
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "tikzimage.tex"
        pdf_path = Path(tmpdir) / "tikzimage.pdf"
        png_path = Path(tmpdir) / "tikzimage.png"
        full_tex = LATEX_TIKZ_TEMPLATE % sanitized_code
        tex_path.write_text(full_tex, encoding="utf-8")
        log.debug(f"[TIKZ] Original code:\n{tikz_code}")
        log.debug(f"[TIKZ] Sanitized code:\n{sanitized_code}")
        log.debug(f"[TIKZ] Full LaTeX file:\n{full_tex}")
        try:
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", str(tex_path)],
                cwd=tmpdir,
                timeout=15,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            log.debug(f"[TIKZ] pdflatex stdout:\n{result.stdout}")
            log.debug(f"[TIKZ] pdflatex stderr:\n{result.stderr}")
            if result.returncode != 0:
                log.error(f"[TIKZ] pdflatex failed with return code {result.returncode}")
                log.error(f"[TIKZ] pdflatex stdout:\n{result.stdout}")
                log.error(f"[TIKZ] pdflatex stderr:\n{result.stderr}")
                return None
        except subprocess.CalledProcessError as e:
            log.error(f"[TIKZ] pdflatex failed:\n{e.stderr}")
            return None
        except subprocess.TimeoutExpired:
            log.error("[TIKZ] pdflatex timed out")
            return None
        except Exception:
            log.exception("[TIKZ] Unexpected error during pdflatex execution")
            return None
        if not pdf_path.exists():
            log.error("[TIKZ] PDF output not found after pdflatex.")
            return None
        try:
            result = subprocess.run(
                [
                    "convert",
                    "-density",
                    "300",
                    "-background",
                    "white",
                    "-alpha",
                    "remove",
                    str(pdf_path),
                    "-quality",
                    "90",
                    str(png_path),
                ],
                timeout=10,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            log.debug(f"[TIKZ] convert stdout:\n{result.stdout}")
            log.debug(f"[TIKZ] convert stderr:\n{result.stderr}")
            if result.returncode != 0:
                log.error(f"[TIKZ] convert failed:\n{result.stderr}")
                return None
        except subprocess.CalledProcessError as e:
            log.error(f"[TIKZ] convert failed:\n{e.stderr}")
            return None
        except subprocess.TimeoutExpired:
            log.error("[TIKZ] convert timed out")
            return None
        except Exception:
            log.exception("[TIKZ] Unexpected error during convert execution")
            return None
        if not png_path.exists():
            log.error("[TIKZ] PNG output not found after convert.")
            return None
        try:
            with open(png_path, "rb") as f:
                file_obj = io.BytesIO(f.read())
            file_obj.seek(0)
            return discord.File(fp=file_obj, filename="tikz.png")
        except Exception:
            log.exception("[TIKZ] Failed to load PNG output into memory")
            return None
