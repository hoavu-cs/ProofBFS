# proof-bfs

proof-bfs is a two-agent proof exploration system: one agent proposes new statements, another checks them, and a goal checker decides when the target is proven or disproven.

[See a demo on YouTube](https://youtu.be/tmGZD796wOs)

## Setup

```bash
pip install -r requirements.txt
```

Requires a `.env` file with `DEEPSEEK_API_KEY=your_key_here`.
You can use any model of your choice by modifying this part of `src\app.py`:

```python
load_dotenv()

deepseek_client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)

ollama_client = OpenAI(
    api_key="ollama",
    base_url="http://localhost:11434/v1",
)

DEEPSEEK_CHAT = "deepseek-chat"
DEEPSEEK_REASONER = "deepseek-reasoner"
OLLAMA_QWEN = "qwen3.5:35b-a3b"
ROUNDS = 10
```

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

## Key files

- `src/app.py`: core loop, prompts, model calls, parsing, logging, save/load helpers.
- `src/tools.py`: `run_python()` and tool schema.
- `src/html_view.py`: generates `{stem}_view.html` with MathJax rendering. This is used to read the math more easily than the JSON.
- `src/proof_cleanup.py`: filters proof chain and exports LaTeX.
- `main.py`: interactive CLI entrypoint.

## Tunable constants

At top of `src/app.py`:

- `ROUNDS`
- `DEEPSEEK_CHAT`, `DEEPSEEK_REASONER`, `OLLAMA_QWEN`
- `deepseek_client`, `ollama_client`
