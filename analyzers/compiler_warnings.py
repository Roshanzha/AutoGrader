"""
compiler_warnings - SYNTAX analyzer.

Compiles the source with the instructor's warning flags and counts warnings.

params:
  flags                : gcc flags, e.g. "-Wall -Wextra -Werror -std=c11"
  penalty_per_warning  : score lost per warning (default 0.1)

Note on -Werror: with -Werror gcc would stop at the first warning and we could
not COUNT them. So we remove -Werror for the count; any error (not warning)
still gives score 0.
"""
import os

import sandbox

NEEDS_EXECUTION = False


def analyze(ctx, params):
    flags = params.get("flags", "-Wall -Wextra -std=c11")
    flags = " ".join(f for f in flags.split() if f != "-Werror")
    penalty = float(params.get("penalty_per_warning", 0.1))

    # "-O2 -c": optimisation enables the flow-analysis warnings; -c = no linking needed
    obj = os.path.join(ctx.workdir, "syntax_check.o")
    res = sandbox.compile_c(ctx.source_path, obj, "-O2 -c " + flags)

    if not res.ok:
        first_error = res.errors[0] if res.errors else res.stderr.strip()[:200]
        return {
            "score": 0.0,
            "evidence": {"compiled": False, "errors": res.errors[:10]},
            "feedback": f"Does not compile: {first_error}",
            "suggestions": ["Fix the compile errors first; nothing else can be run."],
        }

    score = max(0.0, 1.0 - penalty * len(res.warnings))
    return {
        "score": score,
        "evidence": {"compiled": True, "warning_count": len(res.warnings),
                     "warnings": res.warnings[:10], "flags": flags},
        "feedback": (f"{len(res.warnings)} warning(s) with '{flags}'."
                     if res.warnings else f"No warnings with '{flags}'."),
        "suggestions": [w.split(": warning: ", 1)[-1] for w in res.warnings[:5]],
    }
