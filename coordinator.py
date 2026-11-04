"""
coordinator.py - the MAIN AGENT of GraderGent.

One call to grade_submission() does everything, unattended:

  1. LOAD     read the rules file (rules_loader) and the problem files
  2. FIRST PASS  cheap sanity sweep so that no analyzer runs on a submission
                 that cannot even be executed:
                   a) compile check   gcc -O2 -Wall -Wextra -std=c11
                   b) smoke run       sample input, time + memory limits
                   c) static sanity   main() present, a reader, a writer, return in main
  3. DISPATCH run every analyzer named in the rules (in parallel where safe,
                 timing-sensitive ones alone). Execution-based analyzers are
                 SKIPPED if compilation failed or the smoke run timed out
                 (flag: suspected_infinite_loop) -> a PARTIAL report.
  4. COLLATE  weighted grade, failing inputs (+ LLM explanation), flags,
                 usefulness/limitations section; write JSON and text reports.

The grade itself is plain arithmetic over analyzer scores:
    grade = 100 * sum(weight_i * score_i) / sum(weight_i)
so the same submission under the same rules always gives the same grade
(LLM answers are cached; see llm_client.py).
"""
import concurrent.futures
import json
import os
import re
import shutil
import tempfile

import analyzers
import c_source
import explain
import report_writer
import rules_loader
import sandbox
import utils
from context import Context

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_EXPLAINED_FAILURES = 3          # how many failing inputs get an LLM explanation
MAX_PARALLEL_ANALYZERS = 3          # kept low so timing-based limits stay fair

_READERS = r"\b(scanf|fscanf|sscanf|fgets|getchar|getc|fgetc|getline|fread|read|gets)\s*\("
_WRITERS = r"\b(printf|fprintf|puts|putchar|putc|fputc|fputs|fwrite|write)\s*\("


# ----------------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------------
def grade_submission(source_path, rules_path, out_dir=None):
    """
    Grade one C file under one rules file.
    Returns (report_dict, text_report, (json_path, txt_path)).
    Raises rules_loader.RulesError if the rules file is unusable.
    """
    rules = rules_loader.load_rules(rules_path)
    workdir = tempfile.mkdtemp(prefix="gradergent_")     # private scratch space
    try:
        ctx = Context(source_path=source_path, source_text=utils.read_text(source_path),
                      rules=rules, workdir=workdir)
        _load_problem_files(ctx)
        first = first_pass(ctx)
        results = dispatch(ctx, first)
        report = collate(ctx, first, results)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    text = report_writer.render_text(report)
    paths = report_writer.write_reports(report, text, out_dir)
    return report, text, paths


# ----------------------------------------------------------------------------
# Step 1: problem files
# ----------------------------------------------------------------------------
def _load_problem_files(ctx):
    """Read the problem statement and pick the smoke-run sample (first test)."""
    statement = ctx.rules.get("statement_file")
    if statement and os.path.exists(ctx.resolve(statement)):
        ctx.problem_statement = utils.read_text(ctx.resolve(statement))

    if "smoke_input" in ctx.rules:                       # instructor override
        ctx.smoke_input = ctx.rules["smoke_input"]
        return
    for m in ctx.rules["metrics"]:
        if m["analyzer"] == "io_tests":
            tests = utils.load_tests(ctx.resolve(m["params"]["testset_dir"]))
            if tests:
                _, ctx.smoke_input, ctx.smoke_expected = tests[0]
                return


# ----------------------------------------------------------------------------
# Step 2: the first pass (sanity sweep)
# ----------------------------------------------------------------------------
def first_pass(ctx):
    """Compile check, smoke run and static sanity. Returns a dict (goes into the report)."""
    fp = {"compiled": False, "smoke_ok": False, "suspected_infinite_loop": False,
          "static_sanity": {}, "flags": [], "failures": []}

    # (a) compile check - the binary is kept for all execution-based analyzers
    binary = os.path.join(ctx.workdir, "submission.bin")
    build = sandbox.compile_c(ctx.source_path, binary, "-O2 -Wall -Wextra -std=c11")
    fp["compiled"] = build.ok
    fp["compile_warnings"] = len(build.warnings)
    if build.ok:
        ctx.binary_path = binary
    else:
        fp["compile_errors"] = build.errors[:5] or [build.stderr[:300]]
        fp["flags"].append("compile_error: execution-based metrics skipped")

    # (b) smoke run - only if there is something to run
    if build.ok:
        res = sandbox.run_binary(binary, ctx.smoke_input, ctx.time_limit_s, ctx.memory_limit_mb)
        fp["smoke_status"] = res.status
        fp["smoke_ok"] = (res.status == "ok")
        if res.status == "timeout":
            fp["suspected_infinite_loop"] = True
            fp["flags"].append("suspected_infinite_loop: execution-based metrics skipped")
        if not fp["smoke_ok"]:
            fp["failures"].append({
                "test": "Smoke run (sample input)", "input": utils.shorten(ctx.smoke_input),
                "expected": utils.shorten(ctx.smoke_expected), "got": utils.shorten(res.stdout),
                "note": sandbox.describe_run(res)})

    # (c) static sanity - cheap text checks on the source
    clean = c_source.strip_comments_and_strings(ctx.source_text)
    main_funcs = [f for f in c_source.find_functions(ctx.source_text) if f["name"] == "main"]
    sanity = {
        "has_main": bool(main_funcs),
        "has_reader": bool(re.search(_READERS, clean)),
        "has_writer": bool(re.search(_WRITERS, clean)),
        "return_in_main": bool(main_funcs and re.search(r"\breturn\b", main_funcs[0]["body"])),
    }
    fp["static_sanity"] = sanity
    for check, ok in sanity.items():
        if not ok:
            fp["flags"].append(f"static_sanity: {check} is false")
    return fp


# ----------------------------------------------------------------------------
# Step 3: dispatch to the analyzers
# ----------------------------------------------------------------------------
def dispatch(ctx, first):
    """Run every metric's analyzer; returns {metric_name: result_dict}."""
    if not first["compiled"]:
        skip_reason = "the program does not compile"
    elif first["suspected_infinite_loop"]:
        skip_reason = "the program did not finish within the time limit on the sample input"
    else:
        skip_reason = None

    def run_one(metric):
        module = analyzers.REGISTRY[metric["analyzer"]]
        if module.NEEDS_EXECUTION and skip_reason:
            return {"score": 0.0, "evidence": {"skipped": skip_reason},
                    "feedback": f"Skipped: {skip_reason}.", "suggestions": []}
        try:
            result = module.analyze(ctx, metric.get("params", {}))
            result["score"] = max(0.0, min(1.0, float(result.get("score", 0.0))))
            return result
        except Exception as e:      # an analyzer bug must never kill the whole grading
            return {"score": 0.0, "evidence": {"error": repr(e)},
                    "feedback": f"Analyzer '{metric['analyzer']}' could not run: {e}",
                    "suggestions": [],
                    "flags": [f"analyzer_error: {metric['name']}: {e}"]}

    metrics = ctx.rules["metrics"]
    is_serial = lambda m: getattr(analyzers.REGISTRY[m["analyzer"]], "TIMING_SENSITIVE", False)
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PARALLEL_ANALYZERS) as pool:
        futures = {m["name"]: pool.submit(run_one, m) for m in metrics if not is_serial(m)}
        for name, fut in futures.items():
            results[name] = fut.result()
    for m in metrics:                       # timing-sensitive ones: alone, afterwards
        if is_serial(m):
            results[m["name"]] = run_one(m)
    return results


# ----------------------------------------------------------------------------
# Step 4: collation
# ----------------------------------------------------------------------------
def collate(ctx, first, results):
    """Combine analyzer results into the final report dictionary."""
    metrics = ctx.rules["metrics"]
    total_weight = sum(m["weight"] for m in metrics)

    rows, flags, failures, grade = [], list(first["flags"]), list(first["failures"]), 0.0
    flags += [f"rules: {w}" for w in ctx.rules["_warnings"]]
    for m in metrics:
        r = results[m["name"]]
        weight = m["weight"] / total_weight
        contribution = 100.0 * weight * r["score"]
        grade += contribution
        rows.append({
            "name": m["name"], "analyzer": m["analyzer"],
            "score": round(r["score"], 4), "weight": round(weight, 4),
            "contribution": round(contribution, 2),
            "evidence": r.get("evidence", {}), "feedback": r.get("feedback", ""),
            "suggestions": r.get("suggestions", []),
        })
        flags += r.get("flags", [])
        failures += r.get("evidence", {}).get("failing", [])

    # keep one failure per distinct input, explain the first few with the LLM
    unique, seen = [], set()
    for f in failures:
        if f["input"] not in seen:
            seen.add(f["input"])
            unique.append(dict(f))
    for f in unique[:MAX_EXPLAINED_FAILURES]:
        f["why"] = explain.explain_failure(ctx, f)
    unique = unique[:MAX_EXPLAINED_FAILURES]

    ul_path = os.path.join(BASE_DIR, "usefulness_limitations.json")
    usefulness = json.loads(utils.read_text(ul_path)) if os.path.exists(ul_path) else {}

    llm_cfg = ctx.rules.get("llm", {})
    return {
        "submission": os.path.basename(ctx.source_path),
        "source_sha256": utils.sha256_text(ctx.source_text),
        "rules_hash": ctx.rules["_hash"],
        "problem": ctx.rules.get("problem", ""),
        "grade": round(grade, 1),
        "partial": (not first["compiled"]) or first["suspected_infinite_loop"],
        "first_pass": {k: v for k, v in first.items() if k not in ("flags", "failures")},
        "metrics": rows,
        "failures": unique,
        "flags": list(dict.fromkeys(flags)),          # remove duplicates, keep order
        "usefulness_limitations": usefulness,
        "tool_versions": {"gcc": sandbox.tool_version("gcc"),
                          "cppcheck": sandbox.tool_version("cppcheck"),
                          "llm_model": llm_cfg.get("model", "llama3.1"),
                          "llm_temperature": llm_cfg.get("temperature", 0),
                          "llm_seed": llm_cfg.get("seed", 42)},
    }
