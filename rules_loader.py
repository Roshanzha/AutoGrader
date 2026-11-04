"""
rules_loader.py - read and validate the instructor's grading rules.

The rules live in a JSON file OUTSIDE the code (folder rules/), so adding a
metric, changing a weight or a threshold never needs a code change.

Minimal shape of a rules file (see rules/add_rules.json for a full example):
{
  "problem": "add_two_integers",
  "time_limit_s": 1,
  "memory_limit_mb": 64,
  "llm": {"model": "llama3.1", "temperature": 0, "seed": 42},
  "statement_file": "problems/add/statement.txt",       (optional)
  "reference_solution": "problems/add/reference.c",     (needed by edge_case_runner)
  "edge_cases": {"zero": ["0 0"]},                       (optional, named input library)
  "metrics": [
     {"name": "correctness", "analyzer": "io_tests", "weight": 0.2,
      "params": {"testset_dir": "problems/add/tests/"}}
  ]
}
"""
import json

import utils


class RulesError(Exception):
    """The rules file is missing, not valid JSON, or logically wrong."""


def load_rules(path):
    """Return the rules dict (with a few extra '_' keys) or raise RulesError."""
    import analyzers  # imported here to avoid a circular import at start-up

    try:
        raw_text = utils.read_text(path)
        rules = json.loads(raw_text)
    except FileNotFoundError:
        raise RulesError(f"Rules file not found: {path}")
    except ValueError as e:
        raise RulesError(f"Rules file is not valid JSON ({path}): {e}")

    metrics = rules.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise RulesError("Rules need a non-empty 'metrics' list.")

    names = set()
    for m in metrics:
        for key in ("name", "analyzer", "weight"):
            if key not in m:
                raise RulesError(f"Every metric needs '{key}': {m}")
        if m["name"] in names:
            raise RulesError(f"Duplicate metric name: {m['name']}")
        names.add(m["name"])
        if m["analyzer"] not in analyzers.REGISTRY:
            raise RulesError(
                f"Metric '{m['name']}': unknown analyzer '{m['analyzer']}'. "
                f"Available: {', '.join(sorted(analyzers.REGISTRY))}")
        if not isinstance(m["weight"], (int, float)) or m["weight"] < 0:
            raise RulesError(f"Metric '{m['name']}': weight must be a number >= 0")

    total = sum(m["weight"] for m in metrics)
    if total <= 0:
        raise RulesError("The weights add up to 0.")

    warnings = []
    if abs(total - 1.0) > 1e-6:
        warnings.append(f"weights sum to {total:.3f}, not 1.0 - they were normalised")

    # Canonical text -> the hash proves WHICH rules produced a grade.
    rules["_hash"] = "sha256:" + utils.sha256_text(json.dumps(rules, sort_keys=True))
    rules["_path"] = path
    rules["_warnings"] = warnings
    return rules
