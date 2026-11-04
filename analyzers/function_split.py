"""
function_split - MODULARITY analyzer.

Does the student split the work into helper functions, and are those helpers
actually used?

params:
  expect_helpers : if false, this metric always gives full marks
  min_functions  : how many functions (including main) are expected, default 2

Scoring (matches the assignment's example: only main() -> 3/10):
  helpers_needed = min_functions - 1
  no helper at all            -> 0.3
  every needed helper present -> 1.0     (in between: linear)
Only helpers that are CALLED from another function count; a dead function does not.
"""
import re

import c_source

NEEDS_EXECUTION = False


def analyze(ctx, params):
    funcs = c_source.find_functions(ctx.source_text)
    names = [f["name"] for f in funcs]
    min_functions = int(params.get("min_functions", 2))

    if not params.get("expect_helpers", True):
        return {"score": 1.0, "evidence": {"functions_defined": len(funcs)},
                "feedback": "Helpers not required for this problem."}

    # A helper counts only if some OTHER function calls it.
    helpers = [f["name"] for f in funcs if f["name"] != "main"]
    called = [h for h in helpers
              if any(re.search(r"\b" + re.escape(h) + r"\s*\(", f["body"])
                     for f in funcs if f["name"] != h)]

    needed = max(1, min_functions - 1)
    score = 0.3 + 0.7 * min(1.0, len(called) / needed)

    if called and len(called) >= needed:
        feedback = f"Good: {len(funcs)} function(s) defined, helpers in use: {', '.join(called)}."
        suggestions = []
    elif helpers and not called:
        feedback = f"Helper(s) {', '.join(helpers)} defined but never called."
        suggestions = ["Call your helper functions from main (or remove them)."]
    else:
        feedback = f"Only {', '.join(names) or 'no function'} defined; no helper functions."
        suggestions = ["Split the work: extract the core computation into its own function "
                       "(e.g. int add(int a, int b)) and call it from main."]
    return {
        "score": score,
        "evidence": {"functions_defined": len(funcs), "function_names": names,
                     "helpers_called": called, "expected_min": min_functions},
        "feedback": feedback,
        "suggestions": suggestions,
    }
