"""
c_source.py - a very small "C reader" built on regular expressions.

We do NOT need a full C parser. The analyzers only need to know:
  * where the functions are, how long they are, how branchy they are
  * what the comments are
  * a normalised token stream (for similarity checking)

Every analyzer that looks at source code uses these helpers, so the numbers are
consistent between metrics.
"""
import re

# Matches, in one pass: // comments, /* */ comments, "strings" and 'chars'.
# Because strings are matched too, a "//" inside a string is NOT a comment.
_LITERAL_OR_COMMENT = re.compile(
    r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.S)


def strip_comments_and_strings(src):
    """
    Return the source with comments replaced by spaces and string/char
    contents emptied ("..." -> ""). Line numbers stay the same, which lets us
    report correct line positions later.
    """
    def _blank(m):
        t = m.group(0)
        if t.startswith("//") or t.startswith("/*"):
            return re.sub(r"[^\n]", " ", t)   # keep newlines, blank the rest
        return t[0] * 2                        # "" or ''
    return _LITERAL_OR_COMMENT.sub(_blank, src)


def extract_comments(src):
    """List of the comment texts found in the source."""
    return [m.group(0) for m in _LITERAL_OR_COMMENT.finditer(src)
            if m.group(0).startswith(("//", "/*"))]


# ----------------------------------------------------------------------------
# Functions
# ----------------------------------------------------------------------------
_NOT_FUNCTIONS = {"if", "for", "while", "switch", "return", "sizeof", "else", "do"}
_HEADER_RE = re.compile(r"([A-Za-z_]\w*)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*$")


def _match_brace(text, i):
    """Index of the '}' that closes the '{' at position i."""
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return len(text) - 1


def cyclomatic(body):
    """McCabe complexity: 1 + number of decision points inside the body."""
    return 1 + len(re.findall(r"\b(?:if|for|while|case)\b|&&|\|\||\?", body))


def find_functions(src):
    """
    Find all top-level function DEFINITIONS in `src` (comments allowed).

    Returns a list of dicts:
      name, start_line, end_line, length (non-blank lines), cyclomatic, body
    Method: scan the text; every '{' at brace-depth 0 whose preceding text
    looks like `name(args)` starts a function. Blocks like struct/enum/array
    initialisers do not match that shape and are skipped.
    """
    clean = strip_comments_and_strings(src)
    # blank out preprocessor lines (#include, #define ...), keep line numbers
    text = re.sub(r"(?m)^[ \t]*#.*$", lambda m: " " * len(m.group(0)), clean)

    funcs = []
    seg_start = 0   # where the current top-level statement began
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "{":
            end = _match_brace(text, i)
            header = text[seg_start:i].strip()
            m = _HEADER_RE.search(header)
            if m and m.group(1) not in _NOT_FUNCTIONS and "=" not in header.split("(")[0]:
                body = text[i + 1:end]
                # first non-space character of the header = where the function "starts"
                hstart = seg_start + (len(text[seg_start:i]) - len(text[seg_start:i].lstrip()))
                block = text[hstart:end + 1]
                funcs.append({
                    "name": m.group(1),
                    "start_line": text.count("\n", 0, hstart) + 1,
                    "end_line": text.count("\n", 0, end) + 1,
                    "length": sum(1 for l in block.split("\n") if l.strip()),
                    "cyclomatic": cyclomatic(body),
                    "body": body,
                })
            i = end + 1
            seg_start = i
            continue
        if ch == ";":
            seg_start = i + 1
        i += 1
    return funcs


# ----------------------------------------------------------------------------
# Tokens (used by similarity checking and readability heuristics)
# ----------------------------------------------------------------------------
C_KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if", "inline",
    "int", "long", "register", "return", "short", "signed", "sizeof", "static",
    "struct", "switch", "typedef", "union", "unsigned", "void", "volatile",
    "while", "bool", "true", "false",
}
# Library names are kept verbatim: using printf is not "copying".
LIBRARY_NAMES = {
    "main", "printf", "scanf", "fprintf", "fscanf", "sscanf", "sprintf", "snprintf",
    "puts", "gets", "fgets", "fputs", "getchar", "putchar", "malloc", "calloc",
    "realloc", "free", "memset", "memcpy", "strlen", "strcmp", "strcpy", "strncpy",
    "abs", "labs", "pow", "sqrt", "size_t", "FILE", "NULL", "EOF", "stdin", "stdout",
    "stderr", "INT_MAX", "INT_MIN", "LLONG_MAX", "LLONG_MIN", "UINT_MAX",
    "int32_t", "int64_t", "uint32_t", "uint64_t", "qsort", "exit", "atoi",
}
_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|\d+(?:\.\d+)?|==|!=|<=|>=|&&|\|\||\+\+|--|->|<<|>>|\S")


def user_identifiers(src):
    """Names the student invented (variables/functions): not keywords, not library names."""
    clean = strip_comments_and_strings(src)
    clean = re.sub(r"(?m)^[ \t]*#.*$", "", clean)
    names = [t for t in _TOKEN_RE.findall(clean)
             if (t[0].isalpha() or t[0] == "_")
             and t not in C_KEYWORDS and t not in LIBRARY_NAMES]
    return names


def normalized_tokens(src):
    """
    Token stream where student-chosen names become "ID" and numbers become
    "NUM". Two programs that differ only by renamed variables or changed
    constants/comments/whitespace produce the SAME stream - which is exactly
    what we want for copy detection.
    """
    clean = strip_comments_and_strings(src)
    clean = re.sub(r"(?m)^[ \t]*#.*$", "", clean)    # includes/defines carry no signal
    out = []
    for t in _TOKEN_RE.findall(clean):
        if t[0].isalpha() or t[0] == "_":
            out.append(t if (t in C_KEYWORDS or t in LIBRARY_NAMES) else "ID")
        elif t[0].isdigit():
            out.append("NUM")
        else:
            out.append(t)
    return out
