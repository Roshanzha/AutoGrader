"""
io_tests - CORRECTNESS analyzer.

Runs the compiled submission on every test in `testset_dir` (NN.in / NN.out
pairs) and compares the output with the expected output.

params:
  testset_dir : folder holding the .in/.out pairs (relative to project folder)

score = tests_passed / tests_total
"""
import sandbox
import utils

NEEDS_EXECUTION = True


def analyze(ctx, params):
    tests = utils.load_tests(ctx.resolve(params["testset_dir"]))
    if not tests:
        raise ValueError(f"no tests (*.in + *.out) found in {params['testset_dir']}")

    passed = 0
    failing = []
    for name, stdin_text, expected in tests:
        res = sandbox.run_binary(ctx.binary_path, stdin_text,
                                 ctx.time_limit_s, ctx.memory_limit_mb)
        if res.status == "ok" and utils.outputs_match(res.stdout, expected):
            passed += 1
        else:
            failing.append({
                "test": f"Test {name}",
                "input": utils.shorten(stdin_text),
                "expected": utils.shorten(expected),
                "got": utils.shorten(res.stdout),
                "note": sandbox.describe_run(res),
            })

    total = len(tests)
    feedback = f"{passed}/{total} tests pass."
    if failing:
        feedback += f" First failure: {failing[0]['test']} ({failing[0]['note']})."
    return {
        "score": passed / total,
        "evidence": {"tests_passed": passed, "tests_total": total, "failing": failing},
        "feedback": feedback,
        "suggestions": ["Fix the failing inputs listed under 'Where you failed'."] if failing else [],
    }
