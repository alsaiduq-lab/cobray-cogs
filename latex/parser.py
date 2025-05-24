import re

START_CODE_BLOCK_RE = re.compile(r"^((```(la)?tex)(?=\s)|(```))", re.MULTILINE)


def cleanup_code_block(content: str) -> str:
    """Remove Discord-style code block wrappers from LaTeX strings."""
    content = re.sub(r"^```(?:la)?tex\s*", "", content, flags=re.IGNORECASE | re.MULTILINE)
    content = re.sub(r"\s*```$", "", content, flags=re.MULTILINE)
    return content.strip("` \n")


def normalize_infinity(expr: str) -> str:
    """
    Replace 'inf', 'infinity', '∞', etc. with '\\infty' in LaTeX context.
    """
    expr = re.sub(
        r"(?<!\\)\b([+\-])\s*(inf|infinity|∞|infty)\b",
        lambda m: m.group(1) + r"\\infty",
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
    if expr.startswith("$$") and expr.endswith("$$") and len(expr) > 4:
        return expr[2:-2].strip()
    if expr.startswith("$") and expr.endswith("$") and len(expr) > 2:
        return expr[1:-1].strip()
    return expr


def add_latex_linebreaks(latex: str, maxlen: int = 50) -> str:
    """
    Insert LaTeX linebreaks after every maxlen chars for better rendering.
    Only inserts at math-safe boundaries: after a comma, +, -, =, or /.
    """
    if len(latex) <= maxlen:
        return latex
    out = ""
    cur_line_len = 0
    i = 0
    while i < len(latex):
        char = latex[i]
        out += char
        cur_line_len += 1
        if cur_line_len >= maxlen and char in ",+\\-=/" and i < len(latex) - 1:
            out += r"\\ "
            cur_line_len = 0
        i += 1
    return out


def sanitize_tikz_code(code: str) -> str:
    """
    Remove dangerous LaTeX commands/macros from TikZ code for safe compilation.
    """
    dangerous_patterns = [
        r"\\write18\b",
        r"\\input\s*\{[^}]*\}",
        r"\\include\s*\{[^}]*\}",
        r"\\openout\b",
        r"\\openin\b",
    ]
    for pattern in dangerous_patterns:
        code = re.sub(pattern, "", code, flags=re.IGNORECASE)
    code = re.sub(r";\s*", ";\n", code)
    return code.strip()


def normalize_latex(content: str) -> str:
    """Combine all normalization steps for LaTeX rendering."""
    if not content or not isinstance(content, str):
        return ""
    content = cleanup_code_block(content)
    if r"\begin{tikzpicture}" in content or r"\tikz" in content:
        content = normalize_infinity(content)
        content = re.sub(r"[\u200B-\u200D\uFEFF]", "", content)
        content = content.replace("\u2212", "-")
        content = content.replace("\u00a0", " ")
        return content.strip()
    content = strip_dollar_math(content)
    content = normalize_infinity(content)
    content = re.sub(r"[\u200B-\u200D\uFEFF]", "", content)
    content = content.replace("\u2212", "-")
    content = content.replace("\u00a0", " ")
    content = add_latex_linebreaks(content)
    return content.strip()
