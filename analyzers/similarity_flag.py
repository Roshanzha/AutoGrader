"""
similarity_flag - ORIGINALITY analyzer (copy detection).

Two checks, both based on NORMALISED TOKEN 4-GRAMS (see c_source.normalized_tokens):
renaming variables, changing numbers, comments or whitespace does not hide a copy.
Similarity = Jaccard index of the two sets of 4-grams (0 = nothing shared, 1 = identical).

1. CORPUS CHECK  - compare with every *.c file in params["corpus_dir"]
   (other students' submissions; the instructor can also drop solutions
   downloaded from online resources there). If the highest similarity is
   >= flag_threshold  -> the submission is FLAGGED and this metric scores 0.

2. LLM-COPY CHECK (optional, params["llm_baseline"] = true)
   The local LLM writes its own solution(s) to the problem statement; if the
   student's code is >= llm_flag_threshold similar to one of them, the report
   gets an ADVISORY flag "possible_llm_copy". It never lowers the score,
   because this signal is weak (many correct solutions to a tiny problem look
   alike) and a wrong accusation is worse than a missed one.

params:
  corpus_dir          : folder with other .c files
  flag_threshold      : default 0.85
  llm_baseline        : default false
  llm_samples         : how many LLM solutions to generate, default 1
  llm_flag_threshold  : default 0.85
"""
import glob
import os

import c_source
import utils
from llm_client import LLMUnavailable, extract_c_code

NEEDS_EXECUTION = False

PROMPT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "prompts", "solution_system.txt")
K = 4   # n-gram size


def _shingles(src):
    tokens = c_source.normalized_tokens(src)
    if len(tokens) < K:
        return {tuple(tokens)}
    return {tuple(tokens[i:i + K]) for i in range(len(tokens) - K + 1)}


def similarity(src_a, src_b):
    """Jaccard similarity of the token 4-gram sets of two programs (0..1)."""
    a, b = _shingles(src_a), _shingles(src_b)
    return len(a & b) / len(a | b) if (a | b) else 0.0


def analyze(ctx, params):
    threshold = float(params.get("flag_threshold", 0.85))
    flags = []

    # ---- 1. compare with the corpus ---------------------------------------
    best, best_file = 0.0, None
    corpus_dir = params.get("corpus_dir")
    own_path = os.path.abspath(ctx.source_path)
    if corpus_dir:
        for path in sorted(glob.glob(os.path.join(ctx.resolve(corpus_dir), "**", "*.c"),
                                     recursive=True)):
            if os.path.abspath(path) == own_path:
                continue                      # do not compare a file with itself
            sim = similarity(ctx.source_text, utils.read_text(path))
            if sim > best:
                best, best_file = sim, os.path.relpath(path, ctx.resolve(corpus_dir))

    flagged = best >= threshold
    if flagged:
        flags.append(f"possible_copy: {best:.2f} similar to '{best_file}' (threshold {threshold})")

    # ---- 2. compare with LLM-written solutions (advisory only) ------------
    llm_info = "not requested"
    if params.get("llm_baseline", False):
        if not ctx.problem_statement:
            llm_info = "skipped: no statement_file in rules"
        else:
            try:
                llm = ctx.get_llm(params)
                best_llm = 0.0
                for i in range(int(params.get("llm_samples", 1))):
                    user = (f"Problem statement:\n{ctx.problem_statement}\n\n"
                            f"Write solution variant {i + 1}.")
                    solution = extract_c_code(llm.chat(utils.read_text(PROMPT_FILE), user,
                                                       max_tokens=600))
                    best_llm = max(best_llm, similarity(ctx.source_text, solution))
                llm_thr = float(params.get("llm_flag_threshold", 0.85))
                llm_info = f"max similarity to LLM solutions {best_llm:.2f}"
                if best_llm >= llm_thr:
                    flags.append(f"possible_llm_copy (advisory): {best_llm:.2f} similar to "
                                 f"a solution written by {llm.model}")
            except LLMUnavailable:
                llm_info = "skipped: Ollama is not reachable"
                flags.append("llm_unavailable: LLM-copy check skipped")

    return {
        "score": 0.0 if flagged else 1.0,
        "evidence": {"max_similarity": round(best, 3), "most_similar_file": best_file,
                     "flag_threshold": threshold, "llm_check": llm_info},
        "feedback": (f"FLAGGED: {best:.2f} similar to '{best_file}'." if flagged
                     else f"Max similarity {best:.2f} (threshold {threshold}), not flagged."),
        "suggestions": ["Submit your own work; the instructor will review this flag."] if flagged else [],
        "flags": flags,
    }
