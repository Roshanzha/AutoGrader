"""
complexity_estimator - TIME-EFFICIENCY analyzer (empirical).

Method ("timing curve")
-----------------------
1. For every size n in params["sizes"] generate an input of that size
   (deterministic generator chosen by params["input_pattern"]).
2. Run the program `repeats` times per size and keep the MEDIAN wall time.
3. Measure the process start-up cost separately (a run with a minimal input) and
   subtract it, giving "net" times.
4. If the net time never grows above `noise_floor_s`, the program is O(1)
   as far as we can measure.
   Otherwise fit the slope of log(time) vs log(n) and map it to a class:
       slope < 0.5 -> O(log n)     < 1.2 -> O(n)     < 1.6 -> O(n log n)
       slope < 2.4 -> O(n^2)       else  -> O(n^3)
5. Score: full marks if estimated class <= required class; each class worse
   costs 0.5.

Honest warning: this is a measurement, not a proof. Use sizes large enough
that the runtime is visible (milliseconds), otherwise everything looks O(1).
Timing noise is reduced by medians, a noise floor and slope bands - not removed.

params:
  required      : "O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n^2)", "O(n^3)"
  sizes         : list of n values, ascending, e.g. [1000, 10000, 100000]
  input_pattern : two_ints_scaled | n_ints | count_then_ints | one_string
  repeats       : default 3
  noise_floor_s : default 0.02
"""
import math
import statistics

import sandbox

NEEDS_EXECUTION = True
TIMING_SENSITIVE = True      # the coordinator runs this one alone, not in parallel

ORDER = ["O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n^2)", "O(n^3)"]
_KEYS = {o.lower().replace(" ", ""): o for o in ORDER}

# Deterministic input generators: n -> stdin text.
PATTERNS = {
    # two integers of magnitude n                       (e.g. the 'add' problem)
    "two_ints_scaled": lambda n: f"{n} {n}\n",
    # n integers on ONE line
    "n_ints": lambda n: " ".join(str((i * 7919) % 100003) for i in range(n)) + "\n",
    # first line n, then n integers                     (typical "read array" problems)
    "count_then_ints": lambda n: f"{n}\n" + " ".join(str((i * 7919) % 100003) for i in range(n)) + "\n",
    # a single string of n letters
    "one_string": lambda n: "a" * n + "\n",
}


def _normalize(label):
    key = str(label).lower().replace(" ", "")
    if key not in _KEYS:
        raise ValueError(f"unknown complexity '{label}'. Use one of: {', '.join(ORDER)}")
    return _KEYS[key]


def _classify(sizes, times, base, noise_floor):
    """Return (class_name, slope_or_None) from median times and the start-up baseline."""
    net = [max(0.0, t - base) for t in times]
    if max(net) < noise_floor:
        return "O(1)", None
    # only points with a visible net time (>= 1 ms) are usable for a slope
    visible = [(n, t) for n, t in zip(sizes, net) if t >= 0.001]
    if len(visible) >= 2:
        (n1, t1), (n2, t2) = visible[0], visible[-1]
        slope = math.log(t2 / t1) / math.log(n2 / n1)
    else:
        # one visible point: the smaller size was below 1 ms, so this is a LOWER bound
        idx = sizes.index(visible[0][0])
        prev_n = sizes[idx - 1] if idx > 0 else sizes[0] / 2
        slope = math.log(visible[0][1] / 0.001) / math.log(visible[0][0] / prev_n)
    for limit, name in ((0.5, "O(log n)"), (1.2, "O(n)"), (1.6, "O(n log n)"), (2.4, "O(n^2)")):
        if slope < limit:
            return name, slope
    return "O(n^3)", slope


def analyze(ctx, params):
    required = _normalize(params.get("required", "O(n)"))
    sizes = sorted(params.get("sizes", [1000, 10000, 100000]))
    if len(sizes) < 2:
        raise ValueError("'sizes' needs at least two values")
    pattern = params.get("input_pattern", "two_ints_scaled")
    if pattern not in PATTERNS:
        raise ValueError(f"unknown input_pattern '{pattern}'. Use one of: {', '.join(PATTERNS)}")
    repeats = int(params.get("repeats", 3))
    noise_floor = float(params.get("noise_floor_s", 0.02))
    run_limit = ctx.time_limit_s * 3        # a bit more generous than for normal tests

    # start-up baseline: median time of the program on a minimal input
    base_runs = [sandbox.run_binary(ctx.binary_path, PATTERNS[pattern](1), run_limit,
                                    ctx.memory_limit_mb).wall_time for _ in range(repeats)]
    base = statistics.median(base_runs)

    times, used_sizes, problem = [], [], None
    for n in sizes:
        samples = []
        for _ in range(repeats):
            res = sandbox.run_binary(ctx.binary_path, PATTERNS[pattern](n), run_limit,
                                     ctx.memory_limit_mb)
            if res.status == "timeout":
                samples.append(run_limit)
                problem = f"timed out at n={n}"
                break
            if res.status not in ("ok",):
                problem = f"{sandbox.describe_run(res)} at n={n}"
                break
            samples.append(res.wall_time)
        if problem and not samples:
            break
        times.append(statistics.median(samples))
        used_sizes.append(n)
        if problem:
            break   # larger sizes would only be slower

    if len(times) < 2:
        return {"score": 0.0,
                "evidence": {"sizes": used_sizes, "problem": problem},
                "feedback": f"Could not measure growth: program {problem}.",
                "suggestions": ["Make sure the program handles large inputs."]}

    estimated, slope = _classify(used_sizes, times, base, noise_floor)
    gap = ORDER.index(estimated) - ORDER.index(required)
    score = 1.0 if gap <= 0 else max(0.0, 1.0 - 0.5 * gap)

    feedback = f"Estimated {estimated}; required {required}."
    if problem:
        feedback += f" (program {problem})"
    return {
        "score": score,
        "evidence": {"required": required, "estimated": estimated,
                     "slope": None if slope is None else round(slope, 2),
                     "sizes": used_sizes,
                     "median_times_ms": [round(t * 1000, 2) for t in times],
                     "startup_baseline_ms": round(base * 1000, 2),
                     "input_pattern": pattern, "noise_floor_s": noise_floor},
        "feedback": feedback,
        "suggestions": [] if gap <= 0 else
        [f"Your program grows like {estimated} but {required} is required: look for nested loops or repeated work."],
    }
