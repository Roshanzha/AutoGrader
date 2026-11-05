"""Render the same evidence-based result in Gradio and as an offline HTML report."""
from html import escape
import json


def h(value):
    return escape(str(value))


STYLE = """
.gg-result{--gg-bg:#fbfaf7;--gg-fg:#182d35;--gg-line:#c5d2d0;--gg-head:#153b43;--gg-code:#eef2ee;--gg-track:#d8e0de;--gg-bar:#21756f}
.gg-result{box-sizing:border-box;background:var(--gg-bg);color:var(--gg-fg);padding:clamp(16px,4vw,38px);border:1px solid var(--gg-line);border-radius:12px;max-width:1000px;margin:auto;font:16px/1.5 system-ui,sans-serif;overflow-wrap:anywhere}
.gg-result h2,.gg-result h3,.gg-result summary{color:var(--gg-head);font-weight:700}
.gg-result h2{font-size:clamp(24px,4vw,38px);margin:0}
.gg-result h3{font-size:20px;margin:24px 0 8px}
.gg-result p{margin:6px 0}.gg-result details{border-top:1px solid var(--gg-line);padding:10px 0}.gg-result summary{cursor:pointer}
.gg-result pre{white-space:pre-wrap;color:inherit;background:var(--gg-code);padding:10px;border-radius:4px}
.gg-result .gg-row{display:grid;grid-template-columns:minmax(100px,1fr) minmax(50px,2fr) minmax(75px,auto);align-items:center;gap:12px;margin:7px 0}
.gg-result .gg-track{height:12px;background:var(--gg-track);border-radius:3px;overflow:hidden}.gg-result .gg-fill{height:100%;background:var(--gg-bar)}
.gg-result .gg-pts{text-align:right;font-variant-numeric:tabular-nums}
.gg-result ul{padding-left:22px;list-style:disc}
.dark .gg-result{--gg-bg:#15252b;--gg-fg:#e3eef1;--gg-line:#465b62;--gg-head:#a9e6dc;--gg-code:#20333a;--gg-track:#41565c;--gg-bar:#70d6c6}
@media(prefers-color-scheme:dark){body.gg-page{background:#101c21}body.gg-page .gg-result{--gg-bg:#15252b;--gg-fg:#e3eef1;--gg-line:#465b62;--gg-head:#a9e6dc;--gg-code:#20333a;--gg-track:#41565c;--gg-bar:#70d6c6}}
.gg-result :is(p,span,li,strong,pre){color:var(--gg-fg)}
@media print{.gg-result{border:0;padding:0}.gg-track,.gg-fill{print-color-adjust:exact}}
"""


def analysis(report):
    metrics = report["metrics"]
    first = report["first_pass"]
    lines = []
    if report.get("partial"):
        reason = "the initial run timed out" if first["suspected_infinite_loop"] else "compilation failed"
        lines.append(f"This is a partial grade because {reason}. Execution-based checks were skipped.")
    for metric in metrics:
        ev = metric["evidence"]
        if "tests_total" in ev:
            lines.append(f"The program passed {ev['tests_passed']} of {ev['tests_total']} output tests.")
        if ev.get("issues"):
            issue = ev["issues"][0]
            lines.append(f"The memory check detected {issue['issue']} on input {issue['input']!r}.")
    measured = [m for m in metrics if not ({"skipped", "error"} & m["evidence"].keys())]
    if measured:
        worst = max(measured, key=lambda m: 100 * m["weight"] - m["contribution"])
        loss = 100 * worst["weight"] - worst["contribution"]
        if loss >= 0.05:
            lines.append(f"The largest measured deduction was {loss:.1f} points for {worst['name']}. "
                         + worst["feedback"])
        elif len(measured) == len(metrics):
            lines.append("The submission earned full credit on every scored check.")
    return lines


def render_chart(report):
    metrics = report["metrics"]
    parts = [f'<article class="gg-result"><h2>{report["grade"]:.1f} / 100</h2>',
             f'<p>{h(report["submission"])} &middot; {h(report["problem"])}</p>',
             '<h3>Result analysis</h3>']
    parts.extend(f'<p>{h(line)}</p>' for line in analysis(report))
    parts.extend(['<h3>Points earned by metric</h3>',
                  '<p>Each bar shows the share of available points earned for that metric.</p>'])
    for m in metrics:
        pct = 100 * m["score"]
        status = "Skipped" if "skipped" in m["evidence"] else "Analyzer error" if "error" in m["evidence"] else ""
        pts = f'{m["contribution"]:g} / {100*m["weight"]:g}'
        parts.append(f'<div class="gg-row"><span>{h(m["name"])}</span>'
                     f'<div class="gg-track" aria-hidden="true"><div class="gg-fill" style="width:{pct:.2f}%"></div></div>'
                     f'<span class="gg-pts">{status + " · " if status else ""}{pts}</span></div>')
    parts.append('<h3>Test evidence</h3>')
    for f in report["failures"]:
        parts.append(f'<p><strong>{h(f["test"])}</strong></p><pre>Input: {h(f["input"])}\n'
                     f'Expected: {h(f["expected"])}\nActual: {h(f["got"] or "(no output)")}</pre>'
                     f'<p>{h(f.get("why") or f["note"])}</p>')
    if not report["failures"]:
        errors = report["first_pass"].get("compile_errors", [])
        parts.append('<p>' + h(" ".join(errors) or "The checks recorded no failing input.") + '</p>')
    parts.append('<h3>Analyzer findings</h3>')
    for m in metrics:
        parts.append(f'<details><summary>{h(m["name"])} &middot; {h(m["analyzer"])}</summary>'
                     f'<p>{h(m["feedback"])}</p>')
        parts.extend(f'<p>{h(s)}</p>' for s in m["suggestions"])
        parts.append(f'<pre>{h(json.dumps(m["evidence"], indent=2, ensure_ascii=False))}</pre></details>')
    if report["flags"]:
        parts.append('<h3>Flags for review</h3><ul>')
        parts.extend(f'<li>{h(flag)}</li>' for flag in report["flags"])
        parts.append('</ul>')
    for group, title, label, last in [('usefulness','Usefulness','use_case','benefit'),
                                      ('limitations','Limitations','limitation','mitigation')]:
        parts.append(f'<details><summary>{title}</summary>')
        for item in report.get("usefulness_limitations", {}).get(group, []):
            parts.append(f'<p><strong>{h(item[label])}</strong></p><p>{h(item["example"])}</p><p>{h(item[last])}</p>')
        parts.append('</details>')
    parts.append('<details><summary>Run details</summary><pre>' +
                 h(json.dumps({k: report[k] for k in ("first_pass","rules_hash","source_sha256","tool_versions")},
                              indent=2, ensure_ascii=False)) + '</pre></details></article>')
    return ''.join(parts)


def standalone(report):
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" '
            'content="width=device-width,initial-scale=1"><title>AutoGrader report: ' + h(report["submission"])
            + '</title><style>' + STYLE + '</style><body class="gg-page">' + render_chart(report) + '</body></html>')
