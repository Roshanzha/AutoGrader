"""
utils.py - tiny helpers shared by every module.

Nothing in here is "agentic"; these are plain file/text operations:
  * read a file safely
  * hash text (used for rules hash / cache keys)
  * load the test cases (NN.in / NN.out pairs) of a problem
  * compare two program outputs in a forgiving-but-fair way
"""
import glob
import hashlib
import os


def read_text(path):
    """Read a text file. Invalid UTF-8 bytes are replaced instead of crashing."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def sha256_text(text):
    """Hex SHA-256 of a string (used for rules hash, source hash, LLM cache keys)."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def metric_tests(ctx, params):
    """Return validated uploaded tests or the preset's on-disk pairs."""
    if 'uploaded_tests' in params:
        return [(t['id'], t['input'], t['expected']) for t in params['uploaded_tests']]
    return load_tests(ctx.resolve(params['testset_dir']))


def load_tests(testset_dir):
    """
    Load test cases from a directory.

    Convention: every test is a pair  <name>.in  (stdin) and  <name>.out
    (expected stdout), e.g. 01.in / 01.out. Pairs are returned sorted by name
    so the order (and therefore the report) is always the same.

    Returns a list of tuples: (name, stdin_text, expected_stdout_text)
    """
    tests = []
    for in_path in sorted(glob.glob(os.path.join(testset_dir, "*.in"))):
        out_path = in_path[:-3] + ".out"
        if not os.path.exists(out_path):
            continue  # an .in without .out cannot be used as a test
        name = os.path.splitext(os.path.basename(in_path))[0]
        tests.append((name, read_text(in_path), read_text(out_path)))
    return tests


def normalize_output(text):
    """
    Make outputs comparable:
      * Windows line endings -> Unix
      * trailing spaces on each line are ignored
      * trailing blank lines are ignored
    Anything else (case, inner spaces, number formatting) must match exactly.
    """
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def outputs_match(got, expected):
    """True if the student's output equals the expected output after normalisation."""
    return normalize_output(got) == normalize_output(expected)


def shorten(text, limit=300):
    """Trim long strings so reports stay readable."""
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + " ...[truncated]"
