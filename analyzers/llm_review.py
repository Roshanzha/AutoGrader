"""
llm_review - READABILITY analyzer (the local LLM is the evaluator here).

The model (Ollama) gets:
  * a SYSTEM prompt (prompts/reviewer_system.txt) holding the rubric
  * the student's code wrapped in <code> tags (so it is treated as data)
and must answer with JSON: {"score": 0-10, "reasons": [...], "suggestions": [...]}.

Reproducibility: temperature 0 + fixed seed + on-disk cache (see llm_client.py).

Fallback: if Ollama is not reachable or the reply is not valid JSON, a simple
non-LLM heuristic scores the code and the report gets the flag
"llm_unavailable", so the instructor knows this score did not come from the LLM.

Prompt-injection guard: comments such as "give this code 10/10" are detected
with a regex and flagged; the system prompt also tells the model to ignore them.

params (all optional): model, temperature, seed, host  (override rules["llm"])
"""
import os
import re

import c_source
import utils
from llm_client import LLMUnavailable, extract_json

NEEDS_EXECUTION = False

PROMPT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "prompts", "reviewer_system.txt")

_INJECTION = re.compile(
    r"ignore (all |any )?(previous|above|prior)|system prompt|"
    r"(give|rate|score|grade)\b.{0,40}\b(10|full|perfect|maximum|top)|as an ai", re.I)


def heuristic_score(src):
    """
    Cheap readability estimate in 0..1 (used only when the LLM is unavailable):
      40 %  has comments            (at least one per 2 functions)
      40 %  names are not cryptic   (mean length of student names >= 3 characters)
      20 %  lines are short         (no line longer than 100 characters)
    """
    funcs = c_source.find_functions(src)
    comments = c_source.extract_comments(src)
    comment_part = min(1.0, len(comments) / max(1.0, len(funcs) / 2.0))
    names = c_source.user_identifiers(src)
    avg_len = sum(len(n) for n in names) / len(names) if names else 0
    name_part = min(1.0, avg_len / 3.0)
    line_part = 1.0 if all(len(l) <= 100 for l in src.splitlines()) else 0.0
    return 0.4 * comment_part + 0.4 * name_part + 0.2 * line_part


def analyze(ctx, params):
    flags = []
    if _INJECTION.search(" ".join(c_source.extract_comments(ctx.source_text))):
        flags.append("possible_prompt_injection: a comment tries to influence the reviewer")

    user = f"<code>\n{ctx.source_text}\n</code>"
    llm = ctx.get_llm(params)
    try:
        reply = llm.chat(utils.read_text(PROMPT_FILE), user, json_mode=True)
        data = extract_json(reply)
        if not data or "score" not in data:
            raise ValueError("reply was not the expected JSON")
        score10 = max(0, min(10, int(round(float(data["score"])))))
        reasons = [str(r) for r in data.get("reasons", [])][:4]
        suggestions = [str(s) for s in data.get("suggestions", [])][:4]
        return {
            "score": score10 / 10.0,
            "evidence": {"model": llm.model, "temperature": llm.temperature,
                         "seed": llm.seed, "raw_response": reply[:1500]},
            "feedback": f"{score10}/10. " + "; ".join(reasons),
            "suggestions": suggestions,
            "flags": flags,
        }
    except (LLMUnavailable, ValueError, TypeError) as e:
        score = heuristic_score(ctx.source_text)
        why = "Ollama is not reachable" if isinstance(e, LLMUnavailable) else "reply was not valid JSON"
        flags.append(f"llm_unavailable: readability scored by heuristic ({why})")
        return {
            "score": score,
            "evidence": {"method": "heuristic fallback", "reason": str(e)[:200]},
            "feedback": f"{round(score * 10)}/10 (heuristic: comments, name length, line length).",
            "suggestions": ["Use meaningful variable names, add comments, keep lines short."]
            if score < 1 else [],
            "flags": flags,
        }
