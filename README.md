# GraderGent

A rule-driven grading agent for C programs. It compiles and runs a student's `.c` file
in a sandbox, checks it against the instructor's rules, and produces **one grade plus
feedback** (failing inputs with expected output, explanations, suggestions, flags).

Same submission + same rules file => same grade.

## 1. Setup (Ubuntu / Debian)

```bash
sudo apt update
sudo apt install -y gcc cppcheck python3-venv      # cppcheck is optional

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Local LLM (the main evaluator for readability and explanations)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1
```

Ollama must be running (`ollama serve`, or the systemd service the installer creates).
**If it is not running, GraderGent still works**: LLM parts fall back to simple heuristics
and the report gets an `llm_unavailable` flag so you know.

## 2. Run

```bash
python front_app.py                         # web UI at http://127.0.0.1:7860
python front_app.py --cli samples/add_basic.c
python front_app.py --cli samples/*.c --rules rules/add_rules.json
```

Reports are written to `reports/<name>.txt` (for the student) and `reports/<name>.json`
(for machines). `sample_reports/` contains the output for every file in `samples/`
(generated **without** Ollama, so LLM-based parts used the fallback; re-run with Ollama
to see the real thing).

## 3. How it works

```
front_app.py  ->  coordinator.py (main agent)
                    1. rules_loader      read rules/*.json
                    2. first pass        compile check, smoke run, static sanity
                    3. dispatch          analyzers/*  (parallel where safe)
                    4. collate           grade, failures (+LLM "why"), flags, reports
```

If the program does not compile, or the smoke run times out (`suspected_infinite_loop`),
the execution-based analyzers are skipped and a **partial report** is produced; the
source-only analyzers still run.

`grade = 100 * sum(weight_i * score_i) / sum(weight_i)`

| analyzer | metric | method |
|---|---|---|
| `io_tests` | correctness | run every `NN.in`, compare with `NN.out` |
| `compiler_warnings` | syntax | gcc with the rule's flags, each warning costs 0.1 |
| `static_analysis` | structure | cyclomatic complexity + function length (+ cppcheck if installed) |
| `function_split` | modularity | are helper functions defined **and called**? |
| `edge_case_runner` | logical | named edge cases vs. the **reference solution**; optional LLM counter-tests |
| `complexity_estimator` | time efficiency | timing curve, log-log slope -> O(1)/O(n)/O(n^2)... |
| `sanitizer_run` | memory safety | ASan + UBSan + LeakSanitizer on every known input |
| `llm_review` | readability | Ollama with a rubric prompt, temperature 0, fixed seed |
| `similarity_flag` | originality | normalised token 4-gram Jaccard vs. corpus (+ advisory LLM-copy check) |

### Reproducibility
* LLM calls always send `temperature` and `seed`, and answers are **cached** in `.cache/llm/`
  (delete the folder to force fresh answers).
* Edge-case expected outputs come from the reference solution, never from the LLM.
* LLM-proposed counter-tests are shown as extra counter-examples but do **not** change the
  score unless `extra_cases_count_in_score` is `true`.
* The "possible LLM copy" flag is advisory and never lowers the score.
* Timing-based complexity is a measurement and has noise (see limitations in every report).

## 4. The rules file (`rules/*.json`)

Edit these files; no code changes needed. Paths are relative to the project folder.

```json
{
  "problem": "add_two_integers",
  "statement_file": "problems/add/statement.txt",
  "reference_solution": "problems/add/reference.c",
  "time_limit_s": 1,
  "memory_limit_mb": 64,
  "llm": {"host": "http://localhost:11434", "model": "llama3.1", "temperature": 0, "seed": 42},
  "edge_cases": {"zero": ["0 0", "0 5"]},
  "metrics": [
    {"name": "correctness", "analyzer": "io_tests", "weight": 0.2,
     "params": {"testset_dir": "problems/add/tests/"}}
  ]
}
```

Weights should sum to 1.0 (otherwise they are normalised and a note is added to the report).

| analyzer | params |
|---|---|
| `io_tests` | `testset_dir` |
| `compiler_warnings` | `flags`, `penalty_per_warning` (0.1) |
| `static_analysis` | `max_cyclomatic` (8), `max_function_length` (40), `penalty_per_violation`, `penalty_per_cppcheck` |
| `function_split` | `expect_helpers`, `min_functions` (2) |
| `edge_case_runner` | `cases` (names from `edge_cases`, or a `{name: [inputs]}` object), `llm_extra_cases` (0), `extra_cases_count_in_score` (false) |
| `complexity_estimator` | `required`, `sizes`, `input_pattern` (`two_ints_scaled`, `n_ints`, `count_then_ints`, `one_string`), `repeats` (3), `noise_floor_s` (0.02) |
| `sanitizer_run` | `flags`, `penalty_per_issue` (0.3) |
| `llm_review` | optional `model`, `temperature`, `seed`, `host` overrides |
| `similarity_flag` | `corpus_dir`, `flag_threshold` (0.85), `llm_baseline` (false), `llm_samples` (1), `llm_flag_threshold` (0.85) |

LLM behaviour is controlled by the plain-text prompts in `prompts/` (rubric, test designer,
explainer, solution writer) plus `llm` settings above.

### Adding a new problem
1. Create `problems/<name>/` with `statement.txt`, `reference.c`, `tests/NN.in` + `NN.out`.
2. Copy `rules/add_rules.json`, change paths, edge cases, weights.
3. For a problem with larger inputs, choose a matching `input_pattern` and big `sizes`
   for `complexity_estimator` (sizes that run for milliseconds, otherwise everything looks O(1)).
4. To catch copying from online sources, drop known solutions into the `corpus_dir` folder.

### Adding an analyzer (new metric)
Create `analyzers/my_metric.py`:

```python
NEEDS_EXECUTION = False          # True if it must run the compiled binary
def analyze(ctx, params):
    # ctx.source_text, ctx.binary_path, ctx.rules, ctx.get_llm(params), ctx.resolve(path) ...
    return {"score": 0.8, "evidence": {}, "feedback": "short note", "suggestions": []}
```
Then use `"analyzer": "my_metric"` in a rules file. It is discovered automatically.

## 5. Safety note

The sandbox limits time, CPU, memory and output, and kills the whole process group,
so crashing and never-halting programs are handled. **It is not a security boundary.**
Before grading real student code on a shared machine, run GraderGent in a container:

```bash
docker run --rm -it --pids-limit 256 --network none --cap-add=SYS_PTRACE \
  -v "$PWD":/app -w /app python:3.12 bash     # then install gcc, requirements; SYS_PTRACE lets LeakSanitizer work
```
(With `--network none` the container cannot reach Ollama on the host; run Ollama inside it
or use a Docker network instead.)

## 6. Team layout (suggested)

| area | files |
|---|---|
| UI / CLI | `front_app.py` |
| Main agent, reports | `coordinator.py`, `report_writer.py`, `rules_loader.py` |
| Execution safety | `sandbox.py` |
| LLM prompts and client | `llm_client.py`, `explain.py`, `prompts/` |
| Analyzers | `analyzers/*.py` (one owner per file) |
| Rules and problems | `rules/`, `problems/` |

Not included (possible extensions): `valgrind` and `perf`/`oprofile` profiling
(LeakSanitizer covers leaks; instruction counting would make complexity estimates less noisy).
