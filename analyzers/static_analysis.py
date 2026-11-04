"""
static_analysis - STRUCTURE analyzer.

Looks at the source without running it:
  * cyclomatic complexity of every function   (limit: max_cyclomatic)
  * length of every function in lines          (limit: max_function_length)
  * cppcheck findings, IF cppcheck is installed (sudo apt install cppcheck)

params:
  max_cyclomatic        : default 8
  max_function_length   : default 40
  penalty_per_violation : default 0.2   (each function that breaks a limit)
  penalty_per_cppcheck  : default 0.1   (each cppcheck finding)
"""
import shutil
import subprocess

import c_source

NEEDS_EXECUTION = False


def _run_cppcheck(path):
    """Return a list of cppcheck finding strings (empty if the tool is missing)."""
    if not shutil.which("cppcheck"):
        return None   # None = tool not installed
    try:
        p = subprocess.run(
            ["cppcheck", "--enable=warning,style,performance,portability", "--quiet",
             "--template={line}:{severity}:{id}:{message}", path],
            capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return []
    return [l for l in p.stderr.splitlines() if l.strip() and "missingInclude" not in l]


def analyze(ctx, params):
    max_cc = int(params.get("max_cyclomatic", 8))
    max_len = int(params.get("max_function_length", 40))
    funcs = c_source.find_functions(ctx.source_text)

    violations = []
    for f in funcs:
        if f["cyclomatic"] > max_cc:
            violations.append(f"{f['name']}(): cyclomatic complexity {f['cyclomatic']} > {max_cc}")
        if f["length"] > max_len:
            violations.append(f"{f['name']}(): {f['length']} lines > {max_len}")

    cppcheck = _run_cppcheck(ctx.source_path)
    cppcheck_count = len(cppcheck) if cppcheck else 0

    score = 1.0 - float(params.get("penalty_per_violation", 0.2)) * len(violations) \
                - float(params.get("penalty_per_cppcheck", 0.1)) * cppcheck_count
    score = max(0.0, score)

    notes = violations + (cppcheck or [])
    feedback = "Structure is within limits." if not notes else \
        f"{len(violations)} limit violation(s), {cppcheck_count} cppcheck finding(s)."
    return {
        "score": score,
        "evidence": {
            "functions": [{"name": f["name"], "lines": f["length"], "cyclomatic": f["cyclomatic"]}
                          for f in funcs],
            "violations": violations,
            "cppcheck": "not installed" if cppcheck is None else cppcheck,
        },
        "feedback": feedback,
        "suggestions": notes[:5],
    }
