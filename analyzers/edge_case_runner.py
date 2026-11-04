"""
edge_case_runner - LOGICAL analyzer (corner cases and counter-examples).

How it decides who is right
---------------------------
The expected output of every edge case comes from the instructor's REFERENCE
SOLUTION (a correct C program named in the rules: "reference_solution"). The
agent compiles it and runs it on each input. The LLM is never trusted to
compute an expected answer - it only PROPOSES extra inputs.

Two sources of inputs
---------------------
1. Named edge cases from the rules  (params["cases"], looked up in rules["edge_cases"]).
   These decide the score. They are fixed -> the grade is reproducible.
2. Optional LLM "counter-test" inputs (params["llm_extra_cases"] = how many).
   The LLM reads the problem statement + the student's code and proposes
   inputs likely to break THIS program. They show up in the feedback as extra
   counter-examples. They only change the score if
   params["extra_cases_count_in_score"] is true (default false) so that the
   grade does not depend on the LLM's mood.

params:
  cases                      : ["negatives", "zero", ...]  or  {"name": ["input", ...]}
  llm_extra_cases            : int, default 0
  extra_cases_count_in_score : bool, default false
"""
import os

import sandbox
import utils
from llm_client import LLMUnavailable, extract_json

NEEDS_EXECUTION = True

PROMPT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "prompts", "testgen_system.txt")


def _build_reference(ctx):
    """Compile the instructor's reference solution once; return the binary path."""
    ref = ctx.rules.get("reference_solution")
    if not ref:
        raise ValueError("rules need 'reference_solution' (a correct C program) for edge_case_runner")
    out = os.path.join(ctx.workdir, "reference.bin")
    res = sandbox.compile_c(ctx.resolve(ref), out, "-O2 -std=c11")
    if not res.ok:
        raise ValueError("reference solution does not compile: " + res.stderr[:200])
    return out


def _expected_output(ref_bin, stdin_text, ctx):
    """Run the reference. Returns its stdout, or None if it fails (= invalid input)."""
    res = sandbox.run_binary(ref_bin, stdin_text, max(2.0, ctx.time_limit_s * 2), memory_mb=None)
    return res.stdout if res.status == "ok" else None


def _llm_inputs(ctx, params, how_many):
    """Ask the LLM for tricky inputs. Returns a list of strings (may be empty)."""
    llm = ctx.get_llm(params)
    system = utils.read_text(PROMPT_FILE)
    user = (f"Problem statement:\n{ctx.problem_statement or '(not provided)'}\n\n"
            f"Student program:\n<code>\n{ctx.source_text}\n</code>\n\n"
            f"Propose at most {how_many} inputs.")
    data = extract_json(llm.chat(system, user, json_mode=True)) or {}
    inputs = data.get("inputs", [])
    clean = []
    for item in inputs if isinstance(inputs, list) else []:
        if isinstance(item, str) and 0 < len(item) <= 2000:     # sanity limits
            clean.append(item if item.endswith("\n") else item + "\n")
    return clean[:how_many]


def _run_case(ctx, ref_bin, label, stdin_text):
    """Run student and reference on one input. Returns None (skip), or (passed, failure_dict)."""
    expected = _expected_output(ref_bin, stdin_text, ctx)
    if expected is None:
        return None   # reference could not handle it -> not a valid test, ignore
    res = sandbox.run_binary(ctx.binary_path, stdin_text, ctx.time_limit_s, ctx.memory_limit_mb)
    if res.status == "ok" and utils.outputs_match(res.stdout, expected):
        return True, None
    return False, {"test": label, "input": utils.shorten(stdin_text),
                   "expected": utils.shorten(expected), "got": utils.shorten(res.stdout),
                   "note": sandbox.describe_run(res)}


def analyze(ctx, params):
    ref_bin = _build_reference(ctx)

    # ---- 1. named edge cases (these decide the score) ----------------------
    cases = params.get("cases", [])
    named = cases if isinstance(cases, dict) else ctx.named_edge_cases(cases)
    unknown = [] if isinstance(cases, dict) else [c for c in cases if c not in named]

    passed = total = 0
    failing = []
    for case_name, inputs in named.items():
        for k, text in enumerate(inputs, 1):
            text = text if text.endswith("\n") else text + "\n"
            outcome = _run_case(ctx, ref_bin, f"Edge case '{case_name}' #{k}", text)
            if outcome is None:
                continue
            total += 1
            if outcome[0]:
                passed += 1
            else:
                failing.append(outcome[1])
    if total == 0:
        raise ValueError("no usable edge cases (check 'cases' and rules['edge_cases'])")

    # ---- 2. optional LLM counter-tests ------------------------------------
    extra_requested = int(params.get("llm_extra_cases", 0))
    extra_note = "not requested"
    extra_failing = []
    if extra_requested > 0:
        try:
            known = {t for ins in named.values() for t in ins}
            extras = [t for t in _llm_inputs(ctx, params, extra_requested) if t.strip() not in known]
            extra_run = 0
            for k, text in enumerate(extras, 1):
                outcome = _run_case(ctx, ref_bin, f"LLM counter-case #{k}", text)
                if outcome is None:
                    continue
                extra_run += 1
                if not outcome[0]:
                    extra_failing.append(outcome[1])
            extra_note = f"{extra_run} LLM-proposed input(s) run, {len(extra_failing)} failed"
            if params.get("extra_cases_count_in_score", False):
                passed += extra_run - len(extra_failing)
                total += extra_run
                failing += extra_failing
        except LLMUnavailable:
            extra_note = "skipped: Ollama is not reachable"

    score = passed / total
    feedback = f"{passed}/{total} edge cases pass."
    if failing:
        feedback += f" Fails: {failing[0]['test']} (input {failing[0]['input']!r})."
    if extra_failing:
        feedback += f" The LLM also found {len(extra_failing)} counter-example(s)."

    flags = []
    if extra_requested > 0 and extra_note.startswith("skipped"):
        flags.append("llm_unavailable: extra counter-tests skipped")
    return {
        "score": score,
        "evidence": {"cases_passed": passed, "cases_total": total, "unknown_cases": unknown,
                     "llm_extra": extra_note,
                     "failing": failing + ([] if params.get("extra_cases_count_in_score") else extra_failing)},
        "feedback": feedback,
        "suggestions": (["Handle the failing corner cases listed under 'Where you failed'."]
                        if failing or extra_failing else []),
        "flags": flags,
    }
