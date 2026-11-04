"""
explain.py - the "explainer" agent.

For a failing input (input / expected / got) it asks the local LLM to explain
WHY the student's code fails on it, in at most three sentences.

The LLM only writes the explanation. Whether a test failed and what the
expected output is were already decided by deterministic code (tests,
reference solution), so a wrong explanation can never change the grade.

If Ollama is unavailable we fall back to the analyzer's own note, e.g.
"wrong answer" or "crashed (SIGSEGV)".
"""
import os

import utils
from llm_client import LLMUnavailable

PROMPT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "prompts", "explainer_system.txt")


def explain_failure(ctx, failure):
    """Return a short explanation string for one failure dict."""
    user = (f"Problem statement:\n{ctx.problem_statement or '(not provided)'}\n\n"
            f"<code>\n{ctx.source_text}\n</code>\n\n"
            f"INPUT:\n{failure['input']}\n\n"
            f"EXPECTED OUTPUT:\n{failure['expected']}\n\n"
            f"ACTUAL BEHAVIOUR:\n{failure['got'] or '(no output)'}  -- {failure['note']}")
    try:
        text = ctx.get_llm().chat(utils.read_text(PROMPT_FILE), user, max_tokens=250)
        return " ".join(text.split())   # one line, no stray newlines
    except LLMUnavailable:
        return f"{failure['note']} (LLM explanation unavailable - Ollama is not reachable)."
