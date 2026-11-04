"""
sandbox.py - compile and run untrusted student programs SAFELY.

What "safely" means here (Linux only):
  * wall-clock time limit      -> process (and its children) are killed on timeout
  * CPU time limit             -> `ulimit -t`
  * memory limit               -> `ulimit -v` (address space)
  * output size limit          -> `ulimit -f` (stops programs that print forever)
  * own process group/session  -> we can kill the whole group
  * stdin/stdout/stderr go through temporary FILES, never through pipes that
    could fill up and dead-lock us.

IMPORTANT: this protects against buggy programs (infinite loops, crashes,
memory hogs). It is NOT a security boundary against malicious code. For a real
class, run GraderGent itself inside a Docker container or a VM (see README).

We deliberately use `bash -c "ulimit ...; exec binary"` instead of Python's
preexec_fn, because preexec_fn is not safe when several threads exist (the
coordinator runs analyzers in a thread pool).
"""
import math
import os
import shlex
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass

MAX_CAPTURE_BYTES = 1_000_000  # never keep more than ~1 MB of program output


# ----------------------------------------------------------------------------
# Compilation
# ----------------------------------------------------------------------------
@dataclass
class CompileResult:
    ok: bool                 # True if gcc exited with status 0
    stderr: str              # raw compiler messages
    warnings: list          # lines that contain ": warning:"
    errors: list            # lines that contain ": error:"


def compile_c(source, output, flags="-O2 -std=c11", timeout=30):
    """
    Compile `source` with gcc and `flags` into `output`.
    If the flags contain "-c" (object file only) we skip linking (-lm).
    """
    flag_list = shlex.split(flags)
    cmd = ["gcc"] + flag_list + [source, "-o", output]
    if "-c" not in flag_list:
        cmd.append("-lm")  # math library last, so student code can use <math.h>
    # LC_ALL=C forces English messages so that we can find "warning:" reliably.
    env = dict(os.environ, LC_ALL="C")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except FileNotFoundError:
        return CompileResult(False, "gcc not found. Install it: sudo apt install gcc", [], [])
    except subprocess.TimeoutExpired:
        return CompileResult(False, "compiler timed out", [], [])
    lines = p.stderr.splitlines()
    return CompileResult(
        ok=(p.returncode == 0),
        stderr=p.stderr,
        warnings=[l for l in lines if ": warning:" in l],
        errors=[l for l in lines if ": error:" in l],
    )


# ----------------------------------------------------------------------------
# Running
# ----------------------------------------------------------------------------
@dataclass
class RunResult:
    status: str              # ok | timeout | crash | nonzero_exit | output_limit
    stdout: str
    stderr: str
    returncode: int
    wall_time: float         # seconds
    signal_name: str = ""    # e.g. SIGSEGV when status == "crash"


def run_binary(binary, stdin_text="", time_limit_s=1.0, memory_mb=64, env=None,
               output_limit_kb=10240):
    """
    Run `binary` feeding it `stdin_text`.
    memory_mb=None disables the memory limit (needed for AddressSanitizer
    builds, which reserve a huge virtual address space).
    """
    mem = "unlimited" if memory_mb is None else str(int(memory_mb * 1024))  # ulimit -v uses KB
    cpu = str(int(math.ceil(time_limit_s)) + 1)
    script = 'ulimit -v "$1" 2>/dev/null; ulimit -t "$2"; ulimit -f "$3"; exec "$4"'
    cmd = ["/bin/bash", "-c", script, "bash", mem, cpu, str(output_limit_kb),
           os.path.abspath(binary)]
    full_env = dict(os.environ)
    full_env.update(env or {})

    with tempfile.TemporaryFile() as fin, tempfile.TemporaryFile() as fout, \
            tempfile.TemporaryFile() as ferr:
        fin.write(stdin_text.encode("utf-8", errors="replace"))
        fin.flush()
        fin.seek(0)

        start = time.perf_counter()
        proc = subprocess.Popen(cmd, stdin=fin, stdout=fout, stderr=ferr,
                                start_new_session=True, env=full_env)
        timed_out = False
        try:
            proc.wait(timeout=time_limit_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(proc.pid)
            proc.wait()
        wall = time.perf_counter() - start
        _kill_group(proc.pid)   # also stop any child the program left running (fork bombs)

        fout.seek(0)
        ferr.seek(0)
        out = fout.read(MAX_CAPTURE_BYTES).decode("utf-8", errors="replace")
        err = ferr.read(MAX_CAPTURE_BYTES).decode("utf-8", errors="replace")

    rc = proc.returncode
    sig_name = ""
    if timed_out:
        status = "timeout"
    elif rc < 0:                                   # killed by a signal
        sig = -rc
        sig_name = signal.Signals(sig).name if sig in signal.Signals._value2member_map_ else str(sig)
        if sig == signal.SIGXCPU:
            status = "timeout"                     # CPU limit hit
        elif sig == signal.SIGXFSZ:
            status = "output_limit"                # printed too much
        else:
            status = "crash"
    elif rc != 0:
        status = "nonzero_exit"
    else:
        status = "ok"
    return RunResult(status, out, err, rc, wall, sig_name)


def _kill_group(pgid):
    """SIGKILL every process in the program's own process group (ignore 'already gone')."""
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def describe_run(res):
    """One human-readable sentence about how a run ended (used in feedback)."""
    if res.status == "ok":
        note = "wrong answer"
    elif res.status == "timeout":
        note = f"time limit exceeded ({res.wall_time:.2f}s)"
    elif res.status == "crash":
        note = f"crashed ({res.signal_name})"
    elif res.status == "output_limit":
        note = "printed far too much output"
    else:
        note = f"exited with code {res.returncode}"
    # Sanitizer / runtime messages are very informative, keep the first one.
    for line in res.stderr.splitlines():
        if "runtime error" in line or "Sanitizer" in line:
            note += f" [{line.strip()[:150]}]"
            break
    return note


def tool_version(cmd):
    """First line of `<cmd> --version`, or 'not installed'. Used in the report."""
    try:
        p = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=5)
        return (p.stdout or p.stderr).strip().splitlines()[0]
    except Exception:
        return "not installed"
