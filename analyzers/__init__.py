"""
analyzers/ - one module per metric "expert".

AUTO-DISCOVERY: every file in this folder that defines a function
`analyze(ctx, params)` is registered under its file name. So the rules file
can say  "analyzer": "io_tests"  and it finds analyzers/io_tests.py.
To add a new metric you only create a new file here (see README, "Adding an
analyzer"); nothing else has to be edited.

Contract of every analyzer module
---------------------------------
    NEEDS_EXECUTION = True/False      # must the compiled binary be run?
    TIMING_SENSITIVE = True/False     # optional; True => never run in parallel with others

    def analyze(ctx, params) -> dict:
        return {
            "score":       0.0 .. 1.0,        # REQUIRED
            "evidence":    {...},             # raw facts (goes to the JSON report)
            "feedback":    "short sentence",  # shown in the table
            "suggestions": ["...", ...],      # optional, shown under 'Suggestions'
            "flags":       ["..."],           # optional, shown under 'Flags'
        }
    Optional: evidence["failing"] = list of {test, input, expected, got, note}
    which the report prints in the "Where you failed" section.
"""
import importlib
import pkgutil

REGISTRY = {}

for _info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
    if _info.name.startswith("_"):
        continue
    _module = importlib.import_module(f"{__name__}.{_info.name}")
    if hasattr(_module, "analyze"):
        REGISTRY[_info.name] = _module
