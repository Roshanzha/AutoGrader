"""
front_app.py - MAIN FILE of AutoGrader (entry point).

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
import result_analysis

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


def run_grading(c_file, rules_name):
    """
    Called by the UI button.
    Returns (text report, JSON report, [saved file paths]).
    """
    if not c_file:
        return "Please upload a .c file first.", None, None, ""
    if rules_name not in list_rule_files():
        return "Select an available rules file.", None, None, ""
    try:
        report, text, paths = coordinator.grade_submission(
            c_file, os.path.join(RULES_DIR, rules_name))
    except rules_loader.RulesError as e:
        return f"Problem with the rules file: {e}", None, None, ""
    except Exception as e:                                  # never show a stack trace to the user
        return f"Grading failed unexpectedly: {e!r}", None, None, ""
    return text, report, list(paths), result_analysis.render_chart(report)


# ----------------------------------------------------------------------------
# Web UI
# ----------------------------------------------------------------------------
def build_ui():
    import gradio as gr   # imported here so that --cli works without gradio installed

    # All-grey theme: no accent colours.
    theme = gr.themes.Base(primary_hue="gray", secondary_hue="gray", neutral_hue="gray")
    rule_files = list_rule_files()

    with gr.Blocks(title="AutoGrader", theme=theme, css=result_analysis.STYLE) as demo:
        gr.Markdown("# AutoGrader\nRule-driven grading of C programs.")
        gr.HTML('<form method="post" action="/logout"><button type="submit">Sign out</button></form>')
        with gr.Accordion("Agentic AI assignment", open=True):
            gr.Markdown("Read two integers and print their sum. For this assignment, "
                        "use the **Agentic AI assignment** rule set. Upload your C file "
                        "or select the example below, then click **Grade**.")
            gr.File(value=os.path.join(ASSIGNMENT_DIR, "assignment.pdf"),
                    label="Assignment brief", interactive=False)

        with gr.Row():
            c_file = gr.File(label="C submission (.c)", file_types=[".c"], type="filepath")
            with gr.Column():
                choices = [("Agentic AI assignment", name) if name == ASSIGNMENT_RULES
                           else (name, name) for name in rule_files]
                rules = gr.Dropdown(choices=choices,
                                    value=ASSIGNMENT_RULES if ASSIGNMENT_RULES in rule_files
                                    else next(iter(rule_files), None),
                                    label="Rules file (edit the JSON files in rules/)")
                rules_view = gr.Textbox(label="Selected rules (read-only)", lines=10,
                                        interactive=False)

        gr.Examples(examples=[[os.path.join(ASSIGNMENT_DIR, "add.c"), ASSIGNMENT_RULES]],
                    inputs=[c_file, rules], label="Example submission from the assignment")
        run_btn = gr.Button("Grade")
        chart = gr.HTML()
        report_box = gr.Textbox(label="Report", lines=30, max_lines=80, interactive=False)
        json_out = gr.JSON(label="JSON report")
        saved = gr.File(label="Saved report files", file_count="multiple")

        # wiring: what happens when the user does something
        rules.change(show_rules, inputs=rules, outputs=rules_view)
        demo.load(show_rules, inputs=rules, outputs=rules_view)
        run_btn.click(run_grading, inputs=[c_file, rules],
                      outputs=[report_box, json_out, saved, chart])
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
        print(f"[saved: {', '.join(paths)}]\n")
    return status


def main():
    parser = argparse.ArgumentParser(description="AutoGrader - rule-driven C grader")
    parser.add_argument("--cli", nargs="+", metavar="FILE.c",
                        help="grade these files on the command line instead of starting the UI")
    parser.add_argument("--rules", default=os.path.join(RULES_DIR, ASSIGNMENT_RULES),
                        help="rules file for --cli (default: rules/agentic_ai.json)")
    parser.add_argument("--host", default="127.0.0.1", help="UI host (use 0.0.0.0 to share on a LAN)")
    parser.add_argument("--port", type=int, default=7860, help="UI port")
    args = parser.parse_args()

    if args.cli:
        sys.exit(run_cli(args.cli, args.rules))
    import uvicorn
    from web_access import create_app
    uvicorn.run(create_app(build_ui()), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
