"""
context.py - everything one grading run knows, bundled in a single object.

The coordinator builds ONE Context per submission and hands it to every
analyzer together with that analyzer's own `params` slice from the rules file.
Analyzers must treat it as read-only (they run in parallel threads).
"""
import os
from dataclasses import dataclass

import utils
from llm_client import OllamaClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class Context:
    source_path: str            # the student's .c file
    source_text: str            # its content
    rules: dict                 # parsed rules file (see rules_loader.py)
    workdir: str                # private scratch folder for this run
    binary_path: str = None     # compiled -O2 binary (set by the first pass; None if compile failed)
    problem_statement: str = "" # text of the task (optional, used by LLM prompts)
    smoke_input: str = ""       # sample stdin used by the smoke run
    smoke_expected: str = ""    # sample stdout expected for that input

    # ---- convenience accessors for global limits from the rules ----------
    @property
    def time_limit_s(self):
        return float(self.rules.get("time_limit_s", 1))

    @property
    def memory_limit_mb(self):
        return float(self.rules.get("memory_limit_mb", 64))

    # ---- helpers ---------------------------------------------------------
    def resolve(self, path):
        """Paths inside the rules file are relative to the project folder."""
        return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)

    def get_llm(self, params=None):
        """
        Build an Ollama client. Settings come from rules["llm"], and any
        analyzer may override model / temperature / seed in its own params.
        """
        cfg = dict(self.rules.get("llm", {}))
        cfg.update({k: v for k, v in (params or {}).items()
                    if k in ("host", "model", "temperature", "seed")})
        return OllamaClient(host=cfg.get("host", "http://localhost:11434"),
                            model=cfg.get("model", "llama3.1"),
                            temperature=cfg.get("temperature", 0),
                            seed=cfg.get("seed", 42))

    def named_edge_cases(self, names):
        """Resolve edge-case names (e.g. ["zero"]) to {name: [inputs]} using rules["edge_cases"]."""
        lib = self.rules.get("edge_cases", {})
        return {n: lib[n] for n in names if n in lib}

    def known_inputs(self):
        """
        Every input we know about (all test inputs + all edge cases), de-duplicated.
        Used by the sanitizer analyzer, which wants to exercise the program as much as possible.
        Returns a list of (label, stdin_text).
        """
        seen, result = set(), []

        def add(label, text):
            text = text if text.endswith("\n") else text + "\n"
            if text not in seen:
                seen.add(text)
                result.append((label, text))

        for m in self.rules.get("metrics", []):
            if m.get("analyzer") == "io_tests":
                for name, stdin_text, _ in utils.load_tests(self.resolve(m["params"]["testset_dir"])):
                    add(f"test {name}", stdin_text)
        for case_name, inputs in self.rules.get("edge_cases", {}).items():
            for k, text in enumerate(inputs, 1):
                add(f"edge case {case_name} #{k}", text)
        return result
