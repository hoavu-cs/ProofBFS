# proof-bfs

Proof-BFS is a two-agent proof exploration system: one agent proposes new statements, another checks them, and a goal checker decides when the target is proven or disproven.

## High level ideas
- P = {a, b, c} is a pool of facts that could be assumptions or relevant technical results that you know is true
- A goal statement X
- In each round, an agent called Alice will generate an interesting statement z that she thinks is interesting toward proving X
- Bob verifies z. He can either approve, ask for clarification or fix. If there is a bug, Alice has one chance to fix it. If she still fails, move to the next round. The program will stop when the goal or maximum number of rounds is reached.

A few things to keep in mind
* Ensure each newly derived statement is short and easy to verify.
* Even if the final goal isn’t reached, aim for interesting partial results or progress.
* Avoid over-reliance on frontier models; the goal is to help local models achieve respectable performance.
* Be realistic: this approach won’t solve a deep theorem on its own. Current AI likely isn’t at that level yet.
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

This work is mainly tested using DeepSeek's `deepseek-reasoner` since its API exposes chain-of-thought, tool calls, and it is overall a good and inexpensive model to experiment with. I also tested with Gemini-Flash which is weaker while not exposing reasoning traces. Gemini-Pro is probably better but I have not tested on it yet. It is also not clear if it exposes reasoning traces which is important for round-by-round feedback prompt. 

You can in principle add any model to the corresponding code blocks in `src/app.py` and `main.py`.

## Input format

Input is a JSON array of objects with:

- `type`: one of `"definition"`, `"fact"`, `"assumption"`, `"goal"`
- `statement`: required string
- `proof`: optional string
- `comment`: optional string

Example:

```json
[
  {
    "type": "definition",
    "statement": "a, b, c are positive real numbers"
  },
  {
    "type": "fact",
    "statement": "AM-GM inequality: for positive reals x, y, x + y >= 2*sqrt(x*y)"
  },
  {
    "type": "goal",
    "statement": "Prove a target inequality"
  }
]
```

Every statement other than the `goal` is assumed to be true. 

## Running

```bash
python main.py
```

CLI flow:

1. Enter JSON path.
2. Choose proposer model.
3. Choose checker model.
4. Choose whether to open HTML view each round.
5. Choose whether to be prompted for a hint each round.

If hint prompting is enabled, each round asks for optional user guidance. If disabled, the loop runs autonomously until goal reached/disproved or `ROUNDS` is exhausted.

## Output files

All outputs are written next to the input file using the same stem:

| File | Description |
|------|-------------|
| `{stem}_statements.json` | Seed + derived statements (`comment: "Derived"` for new facts) |
| `{stem}_log.txt` | Concise per-round log |
| `{stem}_full_log.txt` | Extended log including reasoning/tool traces |
| `{stem}_view.html` | MathJax HTML view of given facts, derived facts, and goal |

Notes:

- The original input JSON is never modified.
- To continue from previous progress, run again using `{stem}_statements.json` as input.

## Generate LaTeX proof

```bash
python -m src.proof_cleanup
```

Then enter a `{stem}_statements.json` path. The script filters derived statements to those used in the proof chain and writes:

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
- `src/html_view.py`: generates `{stem}_view.html` with MathJax rendering. This is used to read the math more easily than the JSON.
- `src/proof_cleanup.py`: filters proof chain and exports LaTeX.
- `main.py`: interactive CLI entrypoint.

