import sys
import tty
import termios
from pathlib import Path

from rich import print
from rich.console import Console
from rich.rule import Rule

from src.app import DEEPSEEK_CHAT, DEEPSEEK_REASONER, GEMINI_FLASH, GEMINI_PRO, OLLAMA_QWEN, run
from src.goal_latex import generate_proof
from src.txt_to_json import convert

MODELS = [DEEPSEEK_REASONER, DEEPSEEK_CHAT, GEMINI_PRO, GEMINI_FLASH, OLLAMA_QWEN]
TOOLS         = ["run", "txt_to_json", "goal_latex"]
TOOLS_DISPLAY = [
    "run",
    "txt_to_json  (convert input.txt → input.json)",
    "goal_latex   (export filtered LaTeX proof from derived statements)",
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


if __name__ == "__main__":
    console.print(Rule("[bold cyan]∴ ProofBFS[/bold cyan]"))
    print()

    tool = TOOLS[TOOLS_DISPLAY.index(_pick("Tool:", TOOLS_DISPLAY))]
    print()

    if tool == "txt_to_json":
        convert(_require_path("Input .txt path"))

    elif tool == "goal_latex":
        generate_proof(_require_path("Statements JSON path"))

    elif tool == "run":
        path           = _require_path("Input JSON path")
        proposer_model = _pick("Proposer model:", MODELS)
        checker_model  = _pick("Checker model: ", MODELS)
        prompt_rounds  = _pick("Prompt each round for hint:", ["yes", "no"]) == "yes"
        derived_name   = _optional_name("Output statements filename:", path.stem + "_statements.json")
        log_name       = _optional_name("Output log filename:",       path.stem + "_log.txt")
        full_log_name  = _optional_name("Output full log filename:",  path.stem + "_full_log.txt")
        latex_name     = _optional_name("Output LaTeX filename:",     path.stem + "_statements.tex")
        print()
        run(
            path,
            proposer_model=proposer_model,
            checker_model=checker_model,
            prompt_each_round=prompt_rounds,
            derived_name=derived_name,
            log_name=log_name,
            full_log_name=full_log_name,
            latex_name=latex_name,
        )
