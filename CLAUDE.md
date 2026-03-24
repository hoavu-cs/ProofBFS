# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
pip install -r requirements.txt
```

Requires a `.env` file with API keys for the providers you use:
```
DEEPSEEK_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
OPENROUTER_API_KEY=your_key_here
```

You can use any model of your choice by modifying this part of `src/app.py`:

```python
load_dotenv()

deepseek_client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
    base_url="https://api.deepseek.com",
)

ollama_client = OpenAI(
    api_key="ollama",
    base_url="http://localhost:11434/v1",
)

gemini_client = OpenAI(
    api_key=os.environ.get("GEMINI_API_KEY", ""),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

DEEPSEEK_CHAT = "deepseek-chat"
DEEPSEEK_REASONER = "deepseek-reasoner"
OLLAMA_QWEN = "qwen3.5:35b"
GEMINI_FLASH = "gemini-2.5-flash"
GEMINI_PRO = "gemini-2.5-pro"
ROUNDS = 10
```

## Running

```bash
# Main proof assistant (interactive — prompts for JSON path)
python main.py
```

Output files are created alongside the input JSON with suffixes `_statements.json`, `_full_log.txt`, `_log.txt`,and `_view.html`.

If you want a LaTeX document of the proof, try

```bash
python -m src.proof_cleanup 
```
This prompts for the path to a `{stem}_statements.json` file, filters the statements to only those used in the proof chain, and produces a `{stem}_proof.tex` LaTeX document. This is assuming the goal is reached.

## Architecture

The system is a two-agent loop: **Proposer** derives new statements, **Checker** verifies them. A separate **Goal Check** agent tests whether the accumulated facts prove the goal after each approval.

### Key files

- **`src/app.py`** — all business logic: agent prompts, the `chat()` streaming function, `run()` main loop, JSON I/O helpers (`load_statements`, `save_facts`, `append_log`), and the `Fact` dataclass.
- **`src/tools.py`** — defines `run_python()` (executes code in the venv via subprocess) and the `PYTHON_TOOL` OpenAI tool spec. Available packages: `numpy`, `scipy`, `sympy`, `mpmath`, `z3-solver`.
- **`src/proof_cleanup.py`** — post-processing: filters derived statements to only those used in the proof chain, then asks an LLM to produce a compilable LaTeX document.
- **`main.py`** — thin CLI entrypoint, prompts for the JSON path and calls `run()`.
- **`src/html_view.py`** — generates an HTML view of the proof state from `{stem}_statements.json`, showing given facts, derived facts, and the goal. This is used to read the math more easily than the JSON since latex is rendered with MathJax.


### Input / output JSON format

Input JSON: array of objects with `type` (`"definition"`, `"fact"`, `"assumption"`, `"goal"`) and `"statement"`. Optional `"proof"` and `"comment"` fields.

The input file is **never modified**. A `{stem}_statements.json` file is created alongside it on first run, seeded with the input contents. Derived facts are appended there with `"comment": "Derived"`. If you want to continue after a run, use the newly created `{stem}_statements.json` as the input for the next run so that the derived facts are included in the state.

The system allows you to choose if you want to provide a prompt before each round or not. If not, the system will autonomously derive facts until it proves the goal or reaches the `ROUNDS` limit. If you choose to provide a prompt, the system will put your prompt in the context. This allows you to guide the proof search by suggesting which tools to use, which statements to focus on, or even by providing external information.

### Tunable constants (top of `src/app.py`)

- `ROUNDS` — maximum derivation rounds (default 10)
- `DEEPSEEK_CHAT`, `DEEPSEEK_REASONER`, `OLLAMA_QWEN`, `GEMINI_FLASH`, `GEMINI_PRO` — model name constants
- `deepseek_client`, `ollama_client`, `gemini_client` — pre-constructed OpenAI-compatible clients

### `chat()` streaming

`chat()` in `src/app.py` streams responses and handles tool call loops. It prints `reasoning_content` (chain-of-thought) to stdout in real time. The `_full_log` global accumulates thinking and Python execution entries for writing to `{stem}_full_log.txt`.

Models `deepseek-chat`, `deepseek-reasoner`, and `MiniMax-M2` use `user`/`assistant` priming instead of a `system` role (handled in `chat()`).
