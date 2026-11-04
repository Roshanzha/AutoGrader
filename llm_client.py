"""
llm_client.py - the ONLY place that talks to the local LLM (Ollama).

Why a wrapper?
  * every analyzer that uses the LLM gets the same settings handling
  * temperature and seed are always sent (reproducibility)
  * answers are CACHED on disk, keyed by (model, temperature, seed, prompts).
    Same submission + same rules therefore gets the very same LLM answer on
    every run - even if the model would have worded things differently.
    Delete the folder `.cache/llm` to force fresh answers.
  * if Ollama is not running, we raise LLMUnavailable and every analyzer
    falls back to a non-LLM method (and flags it in the report).

Ollama HTTP API used:  POST {host}/api/chat   (default host http://localhost:11434)
"""
import json
import os
import re

import requests

import utils

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Can be moved with the environment variable GRADERGENT_CACHE_DIR (handy for tests / shared servers).
DEFAULT_CACHE_DIR = os.environ.get("GRADERGENT_CACHE_DIR", os.path.join(BASE_DIR, ".cache", "llm"))


class LLMUnavailable(Exception):
    """Raised when Ollama cannot be reached or returns an error."""


class OllamaClient:
    def __init__(self, host="http://localhost:11434", model="llama3.1",
                 temperature=0.0, seed=42, timeout=180, cache_dir=DEFAULT_CACHE_DIR):
        self.host = host.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self.timeout = timeout
        self.cache_dir = cache_dir

    def chat(self, system, user, json_mode=False, max_tokens=800):
        """
        Send one system prompt + one user message, return the model's text.
        json_mode=True asks Ollama to force syntactically valid JSON output.
        """
        # ---- 1. cache lookup -------------------------------------------------
        key = utils.sha256_text(json.dumps(
            [self.model, self.temperature, self.seed, system, user, json_mode, max_tokens]))
        cache_file = os.path.join(self.cache_dir, key + ".txt")
        if os.path.exists(cache_file):
            return utils.read_text(cache_file)

        # ---- 2. real request -------------------------------------------------
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": self.temperature, "seed": self.seed,
                        "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        try:
            r = requests.post(self.host + "/api/chat", json=payload, timeout=self.timeout)
            r.raise_for_status()
            text = r.json()["message"]["content"]
        except (requests.RequestException, KeyError, ValueError) as e:
            raise LLMUnavailable(f"Ollama request failed ({self.host}, model {self.model}): {e}")

        # ---- 3. cache store (only non-empty answers) -------------------------
        if text.strip():
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(text)
        return text


def extract_json(text):
    """
    Pull a JSON object out of an LLM reply. Models sometimes wrap JSON in
    ```json fences or add a sentence before it. Returns a dict or None.
    """
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    m = re.search(r"\{.*\}", text or "", re.S)   # first '{' to last '}'
    if m:
        try:
            return json.loads(m.group(0))
        except ValueError:
            return None
    return None


def extract_c_code(text):
    """Return the code inside the first ``` fence of an LLM reply (or the whole text)."""
    m = re.search(r"```(?:c|C)?\s*\n(.*?)```", text or "", re.S)
    return m.group(1) if m else (text or "")
