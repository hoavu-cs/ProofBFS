# proof-bfs

A two-agent system for exploring mathematical facts using BFS-style search (actually, BFS makes 0 sense because the graph is infinite)
. Starting from a set of seed statements, it iteratively proposes and verifies new statements, building toward a specified goal.

[See a demo on YouTube](https://youtu.be/tmGZD796wOs)

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file with your API key:

```
DEEPSEEK_API_KEY=your_key_here
```

## Input format

Create a JSON file describing your problem. Each entry has a `type` of `"fact"`, `"definition"`, or `"goal"`:

```json

[
  {
    "type": "definition",
    "statement": "a, b, c are positive real numbers",
    "comment": "Domain"
  },
  {
    "type": "fact",
    "statement": "Cauchy-Schwarz inequality (Engel/Titu form): for positive reals x_i, y_i, sum(x_i^2 / y_i) >= (sum x_i)^2 / (sum y_i)",
    "comment": "Key tool"
  },
  {
    "type": "fact",
    "statement": "AM-GM inequality: for positive reals x, y, x + y >= 2*sqrt(x*y), equivalently sqrt(x*y) <= (x+y)/2",
    "comment": "Key tool"
  },
  {
    "type": "fact",
    "statement": "Cauchy-Schwarz in the form: (sum_i u_i * v_i)^2 <= (sum_i u_i^2)(sum_i v_i^2)",
    "comment": "Standard Cauchy-Schwarz"
  },
  {
    "type": "goal",
    "statement": "Prove that a^2/sqrt(3a^2 + 8b^2 + 14ab) + b^2/sqrt(3b^2 + 8c^2 + 14bc) + c^2/sqrt(3c^2 + 8a^2 + 14ca) >= (a+b+c)/5 for all positive reals a, b, c",
    "comment": "VNU entrance exam 2009-2010"
  }
]

```

## Running

```bash
python app.py
```

Enter the path to your input JSON file when prompted. For example:

```
JSON file path: outputs/my_problem.json
```

## Output files

All output files are placed alongside the input JSON, using the same stem:

| File | Contents |
|------|----------|
| `{stem}_statements.json` | All statements (seeds + derived facts) |
| `{stem}_log.txt` | Concise per-round log of proposals and verdicts |
| `{stem}_full_log.txt` | Full log including chain-of-thought reasoning and Python executions |

The input JSON is never modified.

## How it works

Each round:
1. **Proposer** agent reviews all current facts and derives one new statement with proof
2. **Checker** agent reviews the statement and proof, responding with `APPROVED`, `FIX NEEDED`, or `CLARIFICATION NEEDED`
3. If not approved, the proposer revises once and the checker re-evaluates
4. Approved statements are added to the fact pool for subsequent rounds
5. After each approval, a goal checker verifies whether the goal has been reached

Both agents can run Python code for arithmetic, symbolic algebra, and sat solvers: `numpy`, `scipy`, `sympy`, `mpmath`, `z3-solver`.

## Key parameters

Tune these constants at the top of `app.py`:

- `ROUNDS` — maximum number of derivation rounds
