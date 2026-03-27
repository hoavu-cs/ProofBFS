# proof-bfs

Proof-BFS is a two-agent proof exploration system: one agent proposes new statements, another checks them, and a goal checker decides when the target is proven or disproven.

## High level ideas
- P = {a, b, c} is a pool of facts that could be assumptions or relevant technical results that you know is true
- A goal statement X
- In each round, an agent called Alice will generate an interesting statement z that she thinks is interesting toward proving X
- Bob verifies z. He can either approve, ask for clarification or fix. If there is a bug, Alice has one chance to fix it. If she still fails, move to the next round. The program will stop when the goal or maximum number of rounds is reached.
- The agents are allowed to use Python scripts (with libraries like sympy, scipy, mpmath, z3-solver) to verify computations or generate examples/counterexamples. On Linux, these scripts are executed inside a bubblewrap sandbox for security. 

A few things to keep in mind
* Ensure each newly derived statement is short and easy to verify.
* Even if the final goal isn't reached, aim for interesting partial results or progress.
* Avoid over-reliance on frontier models; the goal is to help local models achieve respectable performance.
* Be realistic: this approach won't solve a deep theorem on its own. Current AI likely isn't at that level yet.
* Use it as a helper for proving technical lemmas, and double-check everything carefully.

## Setup

```bash
pip install -r requirements.txt
```

Add API keys for the providers you use to a `.env` file:

```
GEMINI_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
DEEPSEEK_API_KEY=your_key_here
OPENROUTER_API_KEY=your_key_here
```

Some providers and models (configured in `src/app.py`) that were tested. It's fairly easy to add new ones.
DEEPSEEK_REASONER (no quantization) was tested more due to its visible chain-of-thought (to identify weaknesses), decent reasoning, lower cost with no rate limit. GPT5 also works quite well based on my testing. Claude models have rate limit issue for this task.

| Constant | Model | Provider | Reasoning | Notes |
|----------|-------|----------|-----------|-------|
| `DEEPSEEK_REASONER` | `deepseek-reasoner` | DeepSeek | yes | Strong reasoning model; streams chain-of-thought via `reasoning_content` |
| `GEMINI_PRO` | `gemini-2.5-pro` | Google Gemini | yes | Strong reasoning; streams thinking via `reasoning_content` |
| `GEMINI_FLASH` | `gemini-2.5-flash` | Google Gemini | yes | Faster/cheaper Gemini with reasoning |
| `OLLAMA_QWEN` | `qwen3.5:35b` | Ollama (local) | yes | Runs locally; reasoning output wrapped in `<think>` tags |
| `GPT_4O` | `gpt-4o` | OpenAI | no | No visible reasoning |
| `OR_GPT5` | `openai/gpt-5.4` | OpenRouter | no | Capped at 16000 output tokens |

All providers use an OpenAI-compatible client. OpenRouter (`openrouter_client`) is a unified gateway — any model ID from the OpenRouter catalogue works with it. To add another model, create a new constant in `src/app.py` and add it to `MODELS` in `main.py`.

## Input format

Seed files are plain `.txt` files with entries separated by `###` on its own line.

Each entry has the format:
```
Type: statement
Proof: proof text     (optional)
Comment: comment text (optional)
```

Valid types: `Definition`, `Fact`, `Assumption`, `Goal`. Use LaTeX for all mathematical notation. **Every entry other than `Goal` is treated as given and assumed true**. You can also include `Prompt` entries to include additional instructions or guidance for the proposer/checker (not treated as facts).

Example (`examples/inequalities/3/input.txt`):

```
Definition: Let $a, b, c$ be positive real numbers such that $a + b + c \le 2$.
###
Fact: AM-GM inequality: for positive reals $x, y$, $x + y \ge 2\sqrt{xy}$.
Comment: useful inequality
###
Goal: Prove that $\sqrt{a^2 + \frac{1}{b^2}} + \sqrt{b^2 + \frac{1}{c^2}} + \sqrt{c^2 + \frac{1}{a^2}} \ge \frac{\sqrt{97}}{2}$.
```

## Running

```bash
python main.py
```

An interactive menu lets you select a tool:

| Tool | Description |
|------|-------------|
| `run` | Run the proof loop |
| `simplify` | Simplify a completed proof using a proposer/verifier loop |
| `goal_latex` | Export a filtered LaTeX proof from derived statements |
| `statements_latex` | Export all statements and proofs to a `.tex` file |

### `run` options

1. Enter input `.txt` path.
2. Choose proposer and checker models.
3. Choose whether to be prompted for a hint each round.
4. Optionally specify output filenames (press Enter to accept defaults).

If hint prompting is enabled, each round asks for optional user guidance. If disabled, the loop runs autonomously until the goal is reached/disproved or `ROUNDS` is exhausted.

## Output files

All outputs are written next to the input file. During `run`, you are prompted for each output filename — press Enter to accept the default:

| File | Default name | Description |
|------|--------------|-------------|
| Statements | `{stem}_statements.txt` | Seed + all derived statements (`Comment: Derived` for new facts) |
| Full log | `{stem}_full_log.txt` | Extended log including reasoning/tool traces |
| LaTeX | `{stem}_statements.tex` | All statements and proofs, updated after every round |

After a run, derived statements are appended to `{stem}_statements.txt` as new `###`-separated blocks. Example:

```
Fact: $a,b,c > 0$, $a+b+c = abc$ implies $a^2 + b^2 + c^2 \ge 9$, with equality iff $a = b = c = \sqrt{3}$.
Proof: By AM–GM, $a+b+c \ge 3\sqrt[3]{abc}$, so $s^2 \ge 27$. By Cauchy–Schwarz, $a^2+b^2+c^2 \ge s^2/3 \ge 9$.
Comment: Derived
```

Notes:

- The original input `.txt` is never modified.
- To continue from previous progress, run again using the generated `{stem}_statements.txt` as input. It contains all original and derived facts.

## Simplify a proof

Use the `simplify` tool in `main.py`, or run directly:

```bash
python -m src.simplifier
```

Enter a `{stem}_statements.txt` path (must contain a proven goal — i.e., derived statements that prove the goal). The simplifier runs a **proposer/verifier loop**:

1. A **proposer** model reads the original proof and proposes a shorter, more direct proof.
2. A **verifier** model checks correctness and judges whether it is genuinely simpler.
3. This repeats for `SIMPLIFY_ROUNDS` (default 3) rounds, iterating on the best approved proof.

On success, two output files are written next to the input:

| File | Description |
|------|-------------|
| `{stem}_simplified.txt` | Plain-text simplified proof |
| `{stem}_simplified.tex` | LaTeX document with definitions, given facts, and the simplified proof |

If no simplified proof is approved after all rounds, the original remains unchanged.

## Generate filtered LaTeX proof

Use the `goal_latex` tool in `main.py`, or run directly:

```bash
python -m src.goal_latex
```

Enter a `{stem}_statements.txt` path. The script uses an LLM to filter derived statements to those relevant to the proof chain and writes:

- `{stem}_final_proof.tex`

## Architecture

- **Proposer**: derives one statement + proof from current context.
- **Checker**: approves/rejects and can request fixes/clarification.
- **Goal checker**: after each approved statement, decides `PROVEN`, `DISPROVEN`, or `NOT YET`.

Both proposer and checker can use a Python tool (`numpy`, `scipy`, `sympy`, `mpmath`, `z3-solver`) for computations.

### Sandboxing

LLM-generated Python code is executed inside a [bubblewrap](https://github.com/containers/bubblewrap) sandbox when available (Linux only). This blocks network access, prevents filesystem writes outside `/tmp`, and isolates the process using Linux namespaces.

To enable it:

```bash
sudo apt install bubblewrap
```

If `bwrap` is not found, execution falls back to running directly in the venv (no sandboxing). On Windows, the fallback is always used.

## Key files

- `src/app.py`: core loop, prompts, model calls, parsing, logging, save/load helpers.
- `src/tools.py`: `run_python()` and tool schema.
- `src/txt_io.py`: shared parser for the `###`-separated `.txt` format.
- `src/goal_latex.py`: filters proof chain and exports LaTeX.
- `src/statements_latex.py`: exports all statements and proofs to a `.tex` file.
- `src/simplifier.py`: proposer/verifier loop that rewrites a completed proof more simply.
- `main.py`: interactive CLI entrypoint.
