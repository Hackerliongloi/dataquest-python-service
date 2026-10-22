# python-service/main.py
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="DataQuest Python Sandbox")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# The Render build pre-warms matplotlib into this folder so a learner's first
# plot does not spend its whole timeout scanning fonts on a cold instance.
MPL_CONFIG_DIR = os.path.join(BASE_DIR, "mplconfig")
try:
    os.makedirs(MPL_CONFIG_DIR, exist_ok=True)
except OSError:
    pass

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Dataset(BaseModel):
    name: str
    content: str


class RunRequest(BaseModel):
    code: str
    timeout: int = 5
    # Datasets imported in the app are written next to the script so the learner
    # can load them with pd.read_csv(...) / pd.read_json(...) just like locally.
    datasets: list[Dataset] = []


def peak_memory_mb() -> float:
    """Peak RSS of the child process, normalised to MB (platform dependent)."""
    try:
        raw = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    except Exception:
        return 0.0
    # macOS reports bytes, Linux reports kilobytes.
    return round(raw / (1024 * 1024) if sys.platform == "darwin" else raw / 1024, 1)


@app.post("/run")
def run(req: RunRequest):
    timeout = max(1, min(req.timeout, 10))
    start = time.time()
    # A fresh working directory per run: the script and its datasets live
    # together and everything is thrown away afterwards.
    workdir = tempfile.mkdtemp(prefix="dq-")
    script_path = os.path.join(workdir, "main.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(req.code)

    for ds in req.datasets:
        # basename() stops an uploaded path from escaping the sandbox dir.
        safe_name = os.path.basename(ds.name) or "dataset.csv"
        with open(os.path.join(workdir, safe_name), "w", encoding="utf-8") as f:
            f.write(ds.content)

    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
        "MPLBACKEND": "Agg",  # matplotlib never needs a display here
        "MPLCONFIGDIR": MPL_CONFIG_DIR,
    }
    if os.environ.get("HOME"):
        env["HOME"] = os.environ["HOME"]

    try:
        proc = subprocess.run(
            [sys.executable, "main.py"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=workdir,
        )
        duration = int((time.time() - start) * 1000)
        stdout = proc.stdout
        stderr = proc.stderr
        error = None
        if proc.returncode != 0 and not stderr:
            error = f"Process exited with code {proc.returncode}"
        if len(stdout) > 10000:
            stdout = stdout[:10000] + "\n... (truncated)"
        if len(stderr) > 10000:
            stderr = stderr[:10000] + "\n... (truncated)"
        return {
            "stdout": stdout,
            "stderr": stderr,
            "error": error,
            "duration_ms": duration,
            "memory_mb": peak_memory_mb(),
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": "",
            "error": f"Timed out after {timeout}s",
            "duration_ms": int(timeout * 1000),
            "memory_mb": 0.0,
        }
    except Exception as e:
        return {"stdout": "", "stderr": "", "error": str(e), "duration_ms": 0, "memory_mb": 0.0}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
