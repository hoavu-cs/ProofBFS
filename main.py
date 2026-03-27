import sys
import tty
import termios
from pathlib import Path

from rich import print
from rich.console import Console
from rich.rule import Rule

from src.app import (
    DEEPSEEK_REASONER, GEMINI_PRO,
    GPT_4O, OR_GPT5,
    ROUNDS, run,
)
from src.goal_latex import generate_proof
from src.tools import TIMEOUT, set_timeout
from src.statements_latex import generate_statements
from src.simplifier import simplify, SIMPLIFY_ROUNDS

MODELS = [DEEPSEEK_REASONER, GEMINI_PRO, GPT_4O, OR_GPT5]
TOOLS         = ["run", "simplify", "goal_latex", "statements_latex"]
TOOLS_DISPLAY = [
    "run",
    "simplify          (simplify a completed proof)",
    "goal_latex        (export filtered LaTeX proof from derived statements)",
    "statements_latex  (export all statements to LaTeX)",
]
console = Console()

# ANSI helpers (used inside raw-terminal mode where Rich can't write)
_RESET  = "\x1b[0m"
_BOLD   = "\x1b[1m"
_CYAN   = "\x1b[36m"
_DIM    = "\x1b[2m"


def _pick(prompt: str, options: list[str]) -> str:
    """Interactive ↑/↓ selector. Returns the chosen option."""
    idx = 0

    def _render() -> None:
        sys.stdout.write(f"\x1b[2K\r{_BOLD}{prompt}{_RESET}\n")
        for i, opt in enumerate(options):
            if i == idx:
                line = f"  {_CYAN}{_BOLD}❯ {opt}{_RESET}"
            else:
                line = f"  {_DIM}  {opt}{_RESET}"
            sys.stdout.write(f"\x1b[2K\r{line}\n")
        sys.stdout.write(f"\x1b[{len(options) + 1}A")
        sys.stdout.flush()

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        _render()
        while True:
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A":    # up
                        idx = (idx - 1) % len(options)
                    elif ch3 == "B":  # down
                        idx = (idx + 1) % len(options)
            elif ch in ("\r", "\n"):
                break
            elif ch == "\x03":        # Ctrl-C
                raise KeyboardInterrupt
            _render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    # Collapse menu to a single summary line
    sys.stdout.write(f"\x1b[{len(options) + 1}B")
    for _ in range(len(options) + 1):
        sys.stdout.write("\x1b[1A\x1b[2K")
    sys.stdout.write(f"\r{_BOLD}{prompt}{_RESET} {_CYAN}{options[idx]}{_RESET}\n")
    sys.stdout.flush()
    return options[idx]


def _require_path(prompt: str) -> Path:
    path = Path(console.input(f"[bold]{prompt}:[/bold] ").strip())
    if not path.exists():
        print(f"[red]Error: {path} not found.[/red]")
        sys.exit(1)
    return path


def _optional_name(prompt: str, default: str) -> str | None:
    val = console.input(f"[bold]{prompt}[/bold] [dim](Enter for {default})[/dim]: ").strip()
    return val or None


def _ask_int(prompt: str, default: int) -> int:
    val = console.input(f"[bold]{prompt}:[/bold] [dim](Enter for {default})[/dim]: ").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        print(f"[yellow]Invalid number, using default ({default}).[/yellow]")
        return default


if __name__ == "__main__":
    console.print(Rule("[bold cyan]∴ ProofBFS[/bold cyan]"))
    print()

    tool = TOOLS[TOOLS_DISPLAY.index(_pick("Tool:", TOOLS_DISPLAY))]
    print()

    if tool == "simplify":
        path            = _require_path("Statements TXT path")
        proposer_model  = _pick("Proposer model:", MODELS)
        verifier_model  = _pick("Verifier model:", MODELS)
        rounds          = _ask_int("Number of rounds", SIMPLIFY_ROUNDS)
        temperature     = float(console.input(f"[bold]Temperature:[/bold] [dim](Enter for 1.0)[/dim]: ").strip() or "1.0")
        default_out     = path.stem.removesuffix("_statements") + "_simplified.txt"
        out_name        = _optional_name("Output filename:", default_out) or default_out
        print()
        simplify(
            path,
            path.parent / out_name,
            proposer_model=proposer_model,
            verifier_model=verifier_model,
            rounds=rounds,
            temperature=temperature,
        )

    elif tool == "goal_latex":
        generate_proof(_require_path("Statements TXT path"))

    elif tool == "statements_latex":
        generate_statements(_require_path("Statements TXT path"))

    elif tool == "run":
        path           = _require_path("Input .txt path")
        proposer_model = _pick("Proposer model:", MODELS)
        checker_model  = _pick("Checker model: ", MODELS)
        prompt_rounds  = _pick("Prompt each round for hint:", ["yes", "no"]) == "yes"
        rounds         = _ask_int("Number of rounds", ROUNDS)
        temperature    = float(console.input(f"[bold]Temperature:[/bold] [dim](Enter for 1.0)[/dim]: ").strip() or "1.0")
        py_timeout     = _ask_int("Python script timeout (seconds)", TIMEOUT)
        set_timeout(py_timeout)
        derived_name   = _optional_name("Output statements filename:", path.stem + "_statements.txt")
        full_log_name  = _optional_name("Output full log filename:",  path.stem + "_full_log.txt")
        latex_name     = _optional_name("Output LaTeX filename:",     path.stem + "_statements.tex")
        print()
        run(
            path,
            proposer_model=proposer_model,
            checker_model=checker_model,
            prompt_each_round=prompt_rounds,
            rounds=rounds,
            temperature=temperature,
            derived_name=derived_name,
            full_log_name=full_log_name,
            latex_name=latex_name,
        )
