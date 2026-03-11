import sys
import tty
import termios
from pathlib import Path

from rich import print
from rich.console import Console
from rich.rule import Rule

from src.app import DEEPSEEK_CHAT, DEEPSEEK_REASONER, GEMINI_FLASH, GEMINI_PRO, OLLAMA_QWEN, run

MODELS = [DEEPSEEK_REASONER, DEEPSEEK_CHAT, GEMINI_PRO, GEMINI_FLASH, OLLAMA_QWEN]
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


if __name__ == "__main__":
    console.print(Rule("[bold cyan]∴ ProofBFS[/bold cyan]"))

    path_str = console.input("[bold]Input JSON path:[/bold] ").strip()
    path = Path(path_str)
    if not path.exists():
        print(f"[red]Error: {path} not found.[/red]")
        sys.exit(1)

    print()
    proposer_model = _pick("Proposer model:", MODELS)
    checker_model  = _pick("Checker model: ", MODELS)
    open_html      = _pick("Open HTML view:", ["yes", "no"]) == "yes"
    prompt_rounds  = _pick("Prompt each round for hint:", ["yes", "no"]) == "yes"
    print()

    run(
        path,
        proposer_model=proposer_model,
        checker_model=checker_model,
        open_html=open_html,
        prompt_each_round=prompt_rounds,
    )
