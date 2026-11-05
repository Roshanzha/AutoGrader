"""
sanitizer_run - MEMORY-SAFETY analyzer.

Re-compiles the submission with AddressSanitizer + UndefinedBehaviorSanitizer
(gcc -fsanitize=address,undefined) and runs it on EVERY known input (all tests
and all edge cases from the rules). Reports, once per distinct problem:
  * heap/stack/global buffer overflows, use-after-free      (AddressSanitizer)
  * memory leaks                                            (LeakSanitizer, part of ASan)
  * signed overflow, bad shifts, null deref ...             (UBSan: "runtime error: ...")

params:
  flags             : default "-fsanitize=address,undefined"
  penalty_per_issue : score lost per DISTINCT issue, default 0.3

Notes
  * ASan cannot work under a memory (address-space) limit, so memory_mb=None here.
  * LeakSanitizer needs ptrace; in some Docker setups it prints "fatal error".
    Add `--cap-add=SYS_PTRACE` when running the container if leaks are not reported.
"""
import os
import re

import sandbox
import utils

NEEDS_EXECUTION = True

_UBSAN = re.compile(r"runtime error: ([^:\n]+)")
_ASAN = re.compile(r"ERROR: (AddressSanitizer|LeakSanitizer): ([\w-]+)")


def _find_issues(stderr):
    """Extract distinct issue names from sanitizer output."""
    issues = []
    for m in _UBSAN.finditer(stderr):
        issues.append("UBSan: " + m.group(1).strip())
    for m in _ASAN.finditer(stderr):
        if "LeakSanitizer has encountered a fatal error" in stderr:
            continue   # leak checking unavailable here (see module note)
        kind = "memory leak" if m.group(1) == "LeakSanitizer" else m.group(2)
        issues.append(f"{m.group(1)}: {kind}")
    return issues


def analyze(ctx, params):
    flags = params.get("flags", "-fsanitize=address,undefined")
    penalty = float(params.get("penalty_per_issue", 0.3))

    binary = os.path.join(ctx.workdir, "sanitized.bin")
    build = sandbox.compile_c(ctx.source_path, binary,
                              f"-g -O1 -fno-omit-frame-pointer {flags}")
    if not build.ok:
        raise ValueError("sanitizer build failed: " + build.stderr[:300])

    env = {"ASAN_OPTIONS": "detect_leaks=1:color=never", "UBSAN_OPTIONS": "color=never"}
    found = {}      # issue name -> first input that triggers it, and its stderr line
    expected_outputs = {}
    for metric in ctx.rules["metrics"]:
        if metric["analyzer"] == "io_tests":
            tests = utils.load_tests(ctx.resolve(metric["params"]["testset_dir"]))
            expected_outputs.update((stdin.rstrip("\n"), output) for _, stdin, output in tests)
    failing = []
    inputs = ctx.known_inputs() or [("empty input", "")]
    for label, stdin_text in inputs:
        res = sandbox.run_binary(binary, stdin_text, ctx.time_limit_s * 5,
                                 memory_mb=None, env=env)
        for issue in _find_issues(res.stderr):
            if issue not in found:
                line = next((l.strip() for l in res.stderr.splitlines()
                             if "runtime error" in l or "ERROR:" in l or "SUMMARY" in l), "")
                found[issue] = {"issue": issue, "triggered_by": label,
                                "input": stdin_text.strip()[:200], "detail": line[:200]}
                expected = expected_outputs.get(stdin_text.rstrip("\n"))
                if expected is not None:
                    failing.append({"test": f"Sanitizer on {label}", "input": utils.shorten(stdin_text),
                                    "expected": utils.shorten(expected), "got": utils.shorten(res.stdout),
                                    "note": line or issue})

    score = max(0.0, 1.0 - penalty * len(found))
    if found:
        first = next(iter(found.values()))
        feedback = (f"{len(found)} sanitizer issue(s): {', '.join(found)}. "
                    f"First seen on input {first['input']!r}.")
    else:
        feedback = f"Clean under {flags} on {len(inputs)} input(s)."
    return {
        "score": score,
        "evidence": {"inputs_run": len(inputs), "issues": list(found.values()), "failing": failing},
        "feedback": feedback,
        "suggestions": [f"Fix {i['issue']} (input {i['input']!r}): {i['detail']}" for i in found.values()],
    }
