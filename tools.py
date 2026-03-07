import json
import subprocess
from pathlib import Path

VENV_PYTHON = str(Path(__file__).parent / "venv" / "bin" / "python")


def run_python(code: str) -> str:
    result = subprocess.run(
        [VENV_PYTHON, "-c", code],
        capture_output=True, text=True, timeout=5
    )
    return result.stdout.strip() or result.stderr.strip()


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