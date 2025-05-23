import re

START_CODE_BLOCK_RE = re.compile(r"^((```(la)?tex)(?=\s)|(```))", re.MULTILINE)


def cleanup_code_block(content: str) -> str:
    """Remove Discord-style code block wrappers from LaTeX strings."""
    content = re.sub(r"^```(?:la)?tex\s*", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\s*```$", "", content)
    return content.strip("` \n")


def normalize_infinity(expr: str) -> str:
    """
    Replace 'inf', 'infinity', '∞', etc. with '\\infty' in LaTeX context.
    """
    expr = re.sub(
        r"(?<!\\)\b(\+|\-)\s*(inf|infinity|∞|infty)\b",
        lambda m: ("+" if m.group(1) == "+" else "-") + r"\\infty",
        expr,
        flags=re.IGNORECASE,
    )
    expr = re.sub(r"(?<!\\)\b(inf|infinity|∞|infty)\b", r"\\infty", expr, flags=re.IGNORECASE)
    return expr


def strip_dollar_math(expr: str) -> str:
    """
    Remove outer $...$ or $$...$$ math mode if present, to avoid double delimiters.
    """
    expr = expr.strip()
    if expr.startswith("$$") and expr.endswith("$$"):
        return expr[2:-2].strip()
    if expr.startswith("$") and expr.endswith("$"):
        return expr[1:-1].strip()
    return expr


def add_latex_linebreaks(latex: str, maxlen: int = 50) -> str:
    """
    Insert LaTeX linebreaks (\\) after every maxlen chars for better rendering.
    Only inserts at math-safe boundaries: after a comma, +, -, =, or /.
    """
    out = ""
    cur = 0
    for part in re.split(r"([,+\-=/])", latex):
        if cur + len(part) > maxlen and cur > 0:
            out += r"\\ "
            cur = 0
        out += part
        cur += len(part)
    return out


def normalize_latex(content: str) -> str:
    """Combine all normalization steps for LaTeX rendering."""
    content = cleanup_code_block(content)
    content = strip_dollar_math(content)
    content = normalize_infinity(content)
    content = re.sub(r"[\u200B-\u200D\uFEFF]", "", content)
    content = content.replace("\u2212", "-")
    content = add_latex_linebreaks(content)
    return content
