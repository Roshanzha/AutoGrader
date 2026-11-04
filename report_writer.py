"""
report_writer.py - turn the final report dict into files.

Two outputs per submission (same names as in the assignment):
  reports/<name>.json  - for machines (full evidence)
  reports/<name>.txt   - for the student (table, failures, suggestions, flags,
                         usefulness & limitations)
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _block(label, text):
    """'LABEL: text' on one line, or an indented block for multi-line text."""
    text = str(text)
    if "\n" not in text:
        return [f"{label}: {text if text else '(nothing)'}"]
    return [f"{label}:"] + ["    " + line for line in text.splitlines()]


def render_text(report):
    """Build the student-facing text report."""
    out = [f"===== Grading report for {report['submission']} =====",
           f"Overall grade: {report['grade']:.1f} / 100"]
    if report.get("partial"):
        out.append("(PARTIAL REPORT: execution-based metrics were skipped, see Flags)")
    out += ["", f"{'Metric':<16}{'Weight':>7}  {'Points':>9}  Note"]

    for m in report["metrics"]:
        points = f"{m['contribution']:.1f}/{m['weight'] * 100:.0f}"
        out.append(f"{m['name']:<16}{m['weight'] * 100:>6.0f}%  {points:>9}  {m['feedback']}")

    # ---- where the program fails (specific inputs) -----------------------
    out += ["", "--- Where you failed ---"]
    if not report["failures"]:
        errors = report["first_pass"].get("compile_errors")
        if errors:
            out.append("The program does not compile, so it could not be run:")
            out += [f"    {e}" for e in errors]
        else:
            out.append("No failing input was found.")
    for f in report["failures"]:
        out.append(f"{f['test']}")
        out += _block("  INPUT", f["input"])
        out += _block("  EXPECTED", f["expected"])
        out += _block("  GOT", f["got"] or f"({f['note']})")
        out.append(f"  WHY: {f.get('why', f['note'])}")
        out.append("")

    # ---- suggestions ------------------------------------------------------
    out.append("--- Suggestions to raise the grade ---")
    any_suggestion = False
    for m in report["metrics"]:
        if m["score"] < 1.0:
            for s in (m.get("suggestions") or [m["feedback"]]):
                out.append(f"- [{m['name']}] {s}")
                any_suggestion = True
    if not any_suggestion:
        out.append("- Nothing to improve.")

    # ---- flags ------------------------------------------------------------
    if report["flags"]:
        out += ["", "--- Flags (for the instructor) ---"]
        out += [f"- {f}" for f in report["flags"]]

    # ---- usefulness & limitations ----------------------------------------
    ul = report.get("usefulness_limitations", {})
    out += ["", "--- Usefulness & limitations of this evaluation ---", "Useful for:"]
    for i, u in enumerate(ul.get("usefulness", []), 1):
        out += [f"{i}. {u['use_case']}", f"   Example: {u['example']}", f"   Benefit: {u['benefit']}"]
    out += ["", "Limits of this report:"]
    for i, l in enumerate(ul.get("limitations", []), 1):
        out += [f"{i}. {l['limitation']}", f"   Example: {l['example']}", f"   Fix: {l['mitigation']}"]
    return "\n".join(out) + "\n"


def write_reports(report, text, out_dir=None):
    """Write <name>.json and <name>.txt, return their paths."""
    out_dir = out_dir or os.path.join(BASE_DIR, "reports")
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(report["submission"])[0]
    json_path = os.path.join(out_dir, stem + ".json")
    txt_path = os.path.join(out_dir, stem + ".txt")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)
    return json_path, txt_path
