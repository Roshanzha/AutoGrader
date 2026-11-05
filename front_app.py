"""
front_app.py - MAIN FILE of AutoGrader (entry point).

Two ways to use it:

  1) Web UI (Gradio):
         python front_app.py
     then open http://127.0.0.1:7860

  2) Command line (no browser, good for batch grading / scripts / CI):
         python front_app.py --cli samples/add_basic.c --rules rules/add_rules.json
         python front_app.py --cli samples/*.c            (grade several files)

This file only handles input/output (upload, buttons, printing). ALL grading
logic lives in coordinator.py and analyzers/.
"""
import argparse
import glob
import os
import sys
import tempfile
import csv
import json
import zipfile
from pathlib import Path

import coordinator
import rules_loader
import result_analysis
from test_uploads import TestUploadError, load_test_files

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_DIR = os.path.join(BASE_DIR, "rules")
ASSIGNMENT_RULES = "agentic_ai.json"
ASSIGNMENT_DIR = os.path.join(BASE_DIR, "problems", "agentic_ai")


# ----------------------------------------------------------------------------
# Small helpers used by both the UI and the CLI
# ----------------------------------------------------------------------------
def list_rule_files():
    """File names of all rule sets in rules/ (the instructor edits these files)."""
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(RULES_DIR, "*.json")))


def show_rules(rules_name):
    """Text of a rules file, for display in the UI."""
    if rules_name not in list_rule_files():
        return "Select an available rules file."
    try:
        with open(os.path.join(RULES_DIR, rules_name), encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        return f"Cannot read rules file: {e}"


def run_grading(c_file, rules_name, test_files=None):
    """
    Called by the UI button.
    Returns (text report, JSON report, [saved file paths], chart HTML).
    """
    if not c_file:
        return "Please upload a .c file first.", None, None, ""
    if rules_name not in list_rule_files():
        return "Select an available rules file.", None, None, ""
    if not str(c_file).lower().endswith('.c'):
        return "Please upload a C source file ending in .c.", None, None, ""
    try:
        os.makedirs(os.path.join(BASE_DIR, 'reports'), exist_ok=True)
        output = tempfile.mkdtemp(prefix='run_', dir=os.path.join(BASE_DIR, 'reports'))
        report, text, paths = coordinator.grade_submission(
            c_file, os.path.join(RULES_DIR, rules_name), out_dir=output, test_files=test_files)
    except TestUploadError as e:
        return f"Test upload error: {e}", None, None, ""
    except rules_loader.RulesError as e:
        return f"Problem with the rules file: {e}", None, None, ""
    except Exception as e:                                  # never show a stack trace to the user
        return f"Grading failed unexpectedly: {e!r}", None, None, ""
    return text, report, list(paths), result_analysis.render_chart(report)


def run_batch(c_files, rules_name, test_files=None, progress=None):
    """Grade independent submissions with one shared rubric and test selection."""
    if not c_files:
        return 'Upload one or more C files first.', None, None, ''
    if isinstance(c_files, (str, os.PathLike)):
        c_files = [c_files]
    if len(c_files) > 20:
        return 'Upload at most 20 C files per batch.', None, None, ''
    if rules_name not in list_rule_files():
        return 'Select an available grading preset.', None, None, ''
    try:
        for file in c_files:
            if Path(file).suffix.lower() != '.c' or Path(file).stat().st_size > 2*1024*1024:
                raise ValueError('Each submission must be a .c file no larger than 2 MB.')
        load_test_files(test_files)
    except (ValueError, OSError) as exc:
        return f'Upload error: {exc}', None, None, ''

    os.makedirs(os.path.join(BASE_DIR, 'reports'), exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='batch_', dir=os.path.join(BASE_DIR, 'reports')))
    entries, texts, artifacts = [], [], []
    for index, source in enumerate(c_files, 1):
        name = Path(source).name
        if progress:
            progress((index-1, len(c_files)), desc=f'Grading {index}/{len(c_files)}: {name}')
        try:
            text, report, paths, chart = run_grading(source, rules_name, test_files)
        except Exception:
            text, report, paths = 'This submission could not be graded. Try it separately.', None, None
        status = ('Partial' if report.get('partial') else 'Complete') if report else 'Error'
        entry = {'id': index, 'file': name, 'status': status, 'report': report}
        if not report:
            entry['error'] = text
        entries.append(entry)
        texts.append(f'=== {index}. {name} [{status}] ===\n{text}')
        for path in paths or []:
            artifacts.append((path, f'{index:02d}_{Path(source).stem}/{Path(path).name}'))

    summary = {'preset': rules_name, 'submission_count': len(entries), 'submissions': entries}
    json_path, csv_path, zip_path = folder/'batch_results.json', folder/'batch_scores.csv', folder/'all_reports.zip'
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    with csv_path.open('w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Submission', 'File', 'Status', 'Grade / 100'])
        for e in entries:
            # Prevent spreadsheet formula evaluation of user-supplied filenames.
            safe_name = "'"+e['file'] if e['file'].startswith(('=', '+', '-', '@')) else e['file']
            writer.writerow([e['id'], safe_name, e['status'], e['report']['grade'] if e['report'] else ''])
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path, name in artifacts:
            archive.write(path, name)
        archive.write(json_path, json_path.name)
        archive.write(csv_path, csv_path.name)
    if progress:
        progress(1, desc='Batch complete')
    return '\n\n'.join(texts), summary, [str(zip_path), str(csv_path), str(json_path)], result_analysis.render_batch(entries)


# ----------------------------------------------------------------------------
# Web UI
# ----------------------------------------------------------------------------
def build_ui():
    import gradio as gr   # imported here so that --cli works without gradio installed

    # Theme follows the browser's light/dark appearance.
    theme = gr.themes.Base(primary_hue="teal", secondary_hue="cyan", neutral_hue="slate")
    rule_files = list_rule_files()

    with gr.Blocks(title="AutoGrader", theme=theme, css=result_analysis.STYLE) as demo:
        gr.Markdown("# AutoGrader\n### Upload. Evaluate. Understand.\nTeam Everest · C program evaluation with evidence and visual feedback.")
        gr.HTML('<form method="post" action="/logout"><button type="submit">Sign out</button></form>')
        with gr.Accordion("Assignment brief and instructions", open=False):
            gr.Markdown("Read two integers and print their sum. For this assignment, "
                        "use the **Agentic AI assignment** rule set. Upload your C file "
                        "or select the example below, then click **Grade**.")
            gr.File(value=os.path.join(ASSIGNMENT_DIR, "assignment.pdf"),
                    label="Assignment brief", interactive=False)

        with gr.Row():
            with gr.Column():
                gr.Markdown('## 1. Add your submissions')
                c_file = gr.File(label="C submissions (.c) — select multiple files", file_types=[".c"], file_count='multiple', type="filepath")
                gr.Markdown('Upload up to 20 independent C programs (2 MB each). Each is graded separately against the same preset and JSON tests; files are not linked together.')
                test_files = gr.File(label='Optional JSON test files', file_types=['.json'], file_count='multiple', type='filepath')
            with gr.Column():
                gr.Markdown('## 2. Choose the rubric')
                choices = [("Agentic AI assignment", name) if name == ASSIGNMENT_RULES
                           else (name, name) for name in rule_files]
                rules = gr.Dropdown(choices=choices,
                                    value=ASSIGNMENT_RULES if ASSIGNMENT_RULES in rule_files
                                    else next(iter(rule_files), None),
                                    label="Grading preset")
                gr.Markdown('Leave JSON uploads empty to use preset tests. Upload up to 10 files / 100 cases to replace output tests. Other metrics still use this preset; use cases for the same problem.')
                with gr.Accordion('JSON test format and examples', open=False):
                    gr.Code(value='{"tests": [{"input": "2 3\\n", "expected": "5\\n"}]}', language='json', interactive=False)
                    gr.File(value=[os.path.join(BASE_DIR, 'examples/tests/basic.json'), os.path.join(BASE_DIR, 'examples/tests/negative.json')], label='Download sample JSON files', interactive=False, file_count='multiple')
                with gr.Accordion('View rubric configuration', open=False):
                    rules_view = gr.Textbox(label="Selected rules", lines=10, interactive=False)

        gr.Examples(examples=[[[os.path.join(ASSIGNMENT_DIR, "add.c")], ASSIGNMENT_RULES]],
                    inputs=[c_file, rules], label="Example submission from the assignment")
        run_btn = gr.Button("Grade all submissions", variant='primary')
        gr.Markdown('## 3. Compare your results\nView each score in the summary, expand a submission for its pie chart and evidence, then download all reports as a ZIP.')
        chart = gr.HTML()
        saved = gr.File(label="Download batch reports — ZIP, scores CSV, full JSON", file_count="multiple")
        with gr.Accordion('Detailed text report and upload messages', open=True):
            report_box = gr.Textbox(label="Report", lines=8, max_lines=30, interactive=False)
        with gr.Accordion('Structured JSON report', open=False):
            json_out = gr.JSON(label="JSON report")

        # wiring: what happens when the user does something
        rules.change(show_rules, inputs=rules, outputs=rules_view)
        demo.load(show_rules, inputs=rules, outputs=rules_view)
        def grade_batch(files, preset, tests, progress=gr.Progress()):
            return run_batch(files, preset, tests, progress)

        run_btn.click(grade_batch, inputs=[c_file, rules, test_files],
                      outputs=[report_box, json_out, saved, chart])
    return demo


# ----------------------------------------------------------------------------
# Command line
# ----------------------------------------------------------------------------
def run_cli(files, rules_path, test_files=None):
    """Grade each file, print the text report, return a process exit code."""
    status = 0
    for path in files:
        try:
            _, text, paths = coordinator.grade_submission(path, rules_path, test_files=test_files)
        except (rules_loader.RulesError, TestUploadError, OSError) as e:
            print(f"{path}: {e}", file=sys.stderr)
            status = 1
            continue
        print(text)
        print(f"[saved: {', '.join(paths)}]\n")
    return status


def main():
    parser = argparse.ArgumentParser(description="AutoGrader - rule-driven C grader")
    parser.add_argument("--cli", nargs="+", metavar="FILE.c",
                        help="grade these files on the command line instead of starting the UI")
    parser.add_argument("--rules", default=os.path.join(RULES_DIR, ASSIGNMENT_RULES),
                        help="rules file for --cli (default: rules/agentic_ai.json)")
    parser.add_argument("--host", default="127.0.0.1", help="UI host (use 0.0.0.0 to share on a LAN)")
    parser.add_argument('--tests', nargs='+', metavar='TESTS.json', help='optional JSON output-test files for CLI grading')
    parser.add_argument("--port", type=int, default=7860, help="UI port")
    args = parser.parse_args()

    if args.cli:
        sys.exit(run_cli(args.cli, args.rules, args.tests))
    import uvicorn
    from web_access import create_app
    uvicorn.run(create_app(build_ui()), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
