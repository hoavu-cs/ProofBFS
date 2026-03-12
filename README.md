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


[See a demo on YouTube](https://youtu.be/tmGZD796wOs)

## Setup

```bash
pip install -r requirements.txt
```

Add API keys for the providers you use to a `.env` file:

```
DEEPSEEK_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
```

Supported providers and models (configured in `src/app.py`):

| Constant | Model | Provider |
|----------|-------|----------|
| `DEEPSEEK_REASONER` | `deepseek-reasoner` | DeepSeek |
| `DEEPSEEK_CHAT` | `deepseek-chat` | DeepSeek |
| `GEMINI_PRO` | `gemini-2.5-pro` | Google Gemini |
| `GEMINI_FLASH` | `gemini-2.5-flash` | Google Gemini |
| `OLLAMA_QWEN` | `qwen3.5:35b` | Ollama (local) |

All providers use an OpenAI-compatible client. To add another model, create a new client and constant in `src/app.py` and add the model to `MODELS` in `main.py`.

## Input format

Seed files are plain `.txt` files with one entry per line in the format `type: statement`. Lines starting with `#` are treated as comments and attached to the next entry.

Valid types: `definition`, `fact`, `assumption`, `goal`.

Example (`examples/inequalities/7/input.txt`):

```
# Assumption
Assumption: $a, b, c > 0$.

# Assumption
Assumption: $a + b + c = abc$.

# Goal
Goal: Prove that $\frac{1}{1+a^2} + \frac{1}{1+b^2} + \frac{1}{1+c^2} \le \frac{3}{2}$.
```

Use LaTeX for all mathematical notation. Every entry other than `goal` is treated as given and assumed true.

To convert a `.txt` seed file to the `.json` format used internally, use the `txt_to_json` tool in `main.py`. The resulting `input.json`:

```json
[
  { "type": "Assumption", "statement": "$a, b, c > 0$." },
  { "type": "Assumption", "statement": "$a + b + c = abc$." },
  { "type": "Goal", "statement": "Prove that $\\frac{1}{1+a^2} + \\frac{1}{1+b^2} + \\frac{1}{1+c^2} \\le \\frac{3}{2}$." }
]
```

## Running

```bash
python main.py
```

An interactive menu lets you select a tool:

| Tool | Description |
|------|-------------|
| `run` | Run the proof loop |
| `txt_to_json` | Convert a `.txt` seed file to `.json` |
| `goal_latex` | Export a filtered LaTeX proof from derived statements |
| `statements_latex` | Export all statements and proofs to a `.tex` file |

### `run` options

1. Enter input JSON path.
2. Choose proposer and checker models.
3. Choose whether to be prompted for a hint each round.
4. Optionally specify output filenames (press Enter to accept defaults).

If hint prompting is enabled, each round asks for optional user guidance. If disabled, the loop runs autonomously until the goal is reached/disproved or `ROUNDS` is exhausted.

## Output files

All outputs are written next to the input file. During `run`, you are prompted for each output filename — press Enter to accept the default:

| File | Default name | Description |
|------|--------------|-------------|
| Statements JSON | `{stem}_statements.json` | Seed + all derived statements (`comment: "Derived"` for new facts) |
| Full log | `{stem}_full_log.txt` | Extended log including reasoning/tool traces |
| LaTeX | `{stem}_statements.tex` | All statements and proofs, updated after every round |

After a run, derived statements are appended to `{stem}_statements.json`. Example entry from `examples/inequalities/7/statements1.json`:

```json
{
  "type": "fact",
  "statement": "$a,b,c > 0$, $a+b+c = abc$ implies $a^2 + b^2 + c^2 \\ge 9$, with equality iff $a = b = c = \\sqrt{3}$.",
  "proof": "By AM–GM, $a+b+c \\ge 3\\sqrt[3]{abc}$, so $s^2 \\ge 27$. By Cauchy–Schwarz, $a^2+b^2+c^2 \\ge s^2/3 \\ge 9$.",
  "comment": "Derived"
}
```

Notes:

- The original input JSON is never modified.
- To continue from previous progress, run again using the newly generated JSON. This new JSON contains all original and derived facts.

## Generate filtered LaTeX proof

Use the `goal_latex` tool in `main.py`, or run directly:

```bash
python -m src.goal_latex
```

Enter a `{stem}_statements.json` path. The script uses an LLM to filter derived statements to those relevant to the proof chain and writes:

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
- `src/goal_latex.py`: filters proof chain and exports LaTeX.
- `src/statements_latex.py`: exports all statements and proofs to a `.tex` file.
- `src/txt_to_json.py`: converts `.txt` seed files to `.json`.
- `main.py`: interactive CLI entrypoint.
