import shutil
import subprocess
from pathlib import Path

VENV_PYTHON = str(Path(__file__).parent.parent / "venv" / "bin" / "python")
TIMEOUT = 20


def set_timeout(seconds: int) -> None:
    global TIMEOUT
    TIMEOUT = seconds


def _bwrap_cmd(python_args: list[str]) -> list[str]:
    """Wrap a command in a bubblewrap sandbox: no network, no PIDs, read-only FS."""
    venv_dir = str(Path(__file__).parent.parent / "venv")
    cmd = ["bwrap"]
    for d in ["/usr", "/bin", "/lib", "/lib64", "/etc/ld.so.cache"]:
        if Path(d).exists():
            cmd += ["--ro-bind", d, d]
    cmd += [
        "--ro-bind", venv_dir, venv_dir,
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--unshare-net",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--die-with-parent",
        "--",
        *python_args,
    ]
    return cmd


def run_python(code: str) -> str:
    python_args = [VENV_PYTHON, "-c", code]
    cmd = _bwrap_cmd(python_args) if shutil.which("bwrap") else python_args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        return result.stdout.strip() or result.stderr.strip()
    except subprocess.TimeoutExpired:
        return f"TimeoutError: code execution exceeded {TIMEOUT}s"


PYTHON_TOOL = {
    "type": "function",
    "function": {
        "name": "run_python",
        "description": "Executes a Python code snippet and returns the output or error message.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The Python code snippet to execute."
                }
            },
            "required": ["code"]
        }
    }
}
