"""
front_app.py - MAIN FILE of GraderGent (entry point).

Two ways to use it:

  1) Web UI (Gradio, plain and colourless):
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

import coordinator
import rules_loader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_DIR = os.path.join(BASE_DIR, "rules")


# ----------------------------------------------------------------------------
# Small helpers used by both the UI and the CLI
# ----------------------------------------------------------------------------
def list_rule_files():
    """File names of all rule sets in rules/ (the instructor edits these files)."""
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(RULES_DIR, "*.json")))


def show_rules(rules_name):
    """Text of a rules file, for display in the UI."""
    try:
        with open(os.path.join(RULES_DIR, rules_name), encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        return f"Cannot read rules file: {e}"


def run_grading(c_file, rules_name):
    """
    Called by the UI button.
    Returns (text report, JSON report, [saved file paths]).
    """
    if not c_file:
        return "Please upload a .c file first.", None, None
    if not rules_name:
        return "No rules file found in rules/.", None, None
    try:
        report, text, paths = coordinator.grade_submission(
            c_file, os.path.join(RULES_DIR, rules_name))
    except rules_loader.RulesError as e:
        return f"Problem with the rules file: {e}", None, None
    except Exception as e:                                  # never show a stack trace to the user
        return f"Grading failed unexpectedly: {e!r}", None, None
    return text, report, list(paths)


# ----------------------------------------------------------------------------
# Web UI
# ----------------------------------------------------------------------------
def build_ui():
    import gradio as gr   # imported here so that --cli works without gradio installed

    # All-grey theme: no accent colours.
    theme = gr.themes.Base(primary_hue="gray", secondary_hue="gray", neutral_hue="gray")
    rule_files = list_rule_files()

    with gr.Blocks(title="GraderGent", theme=theme) as demo:
        gr.Markdown("# GraderGent\nRule-driven grading of C programs.")

        with gr.Row():
            c_file = gr.File(label="C submission (.c)", file_types=[".c"], type="filepath")
            with gr.Column():
                rules = gr.Dropdown(choices=rule_files,
                                    value=rule_files[0] if rule_files else None,
                                    label="Rules file (edit the JSON files in rules/)")
                rules_view = gr.Textbox(label="Selected rules (read-only)", lines=10,
                                        interactive=False)

        run_btn = gr.Button("Grade")
        report_box = gr.Textbox(label="Report", lines=30, max_lines=80, interactive=False)
        json_out = gr.JSON(label="JSON report")
        saved = gr.File(label="Saved report files", file_count="multiple")

        # wiring: what happens when the user does something
        rules.change(show_rules, inputs=rules, outputs=rules_view)
        demo.load(show_rules, inputs=rules, outputs=rules_view)
        run_btn.click(run_grading, inputs=[c_file, rules],
                      outputs=[report_box, json_out, saved])
    return demo


# ----------------------------------------------------------------------------
# Command line
# ----------------------------------------------------------------------------
def run_cli(files, rules_path):
    """Grade each file, print the text report, return a process exit code."""
    status = 0
    for path in files:
        try:
            _, text, paths = coordinator.grade_submission(path, rules_path)
        except (rules_loader.RulesError, OSError) as e:
            print(f"{path}: {e}", file=sys.stderr)
            status = 1
            continue
        print(text)
        print(f"[saved: {paths[0]} , {paths[1]}]\n")
    return status


def main():
    parser = argparse.ArgumentParser(description="GraderGent - rule-driven C grader")
    parser.add_argument("--cli", nargs="+", metavar="FILE.c",
                        help="grade these files on the command line instead of starting the UI")
    parser.add_argument("--rules", default=os.path.join(RULES_DIR, "add_rules.json"),
                        help="rules file for --cli (default: rules/add_rules.json)")
    parser.add_argument("--host", default="127.0.0.1", help="UI host (use 0.0.0.0 to share on a LAN)")
    parser.add_argument("--port", type=int, default=7860, help="UI port")
    args = parser.parse_args()

    if args.cli:
        sys.exit(run_cli(args.cli, args.rules))
    build_ui().launch(server_name=args.host, server_port=args.port)


if __name__ == "__main__":
    main()
