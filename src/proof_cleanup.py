import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)

FILTER_SYSTEM = """\
You are a mathematical proof editor. You will be given a goal and a list of derived statements (numbered from 1).
Your job: identify which statements are actually used in a valid proof of the goal.
Discard any statements that are dead ends, redundant, or not part of the final proof chain.
Respond with ONLY a JSON array of the indices (1-based) of the statements to keep, in the order they should appear.
Example: [2, 4, 5]"""


def _filter_statements(goal: str, derived: list[dict]) -> list[dict]:
    numbered = "\n".join(
        f"{i}. {e['statement']}\n   Proof: {e.get('proof', '')}"
        for i, e in enumerate(derived, start=1)
    )
    prompt = f"Goal: {goal}\n\nDerived statements:\n{numbered}\n\nWhich indices are needed for the proof?"
    response = _client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": FILTER_SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
    raw = response.choices[0].message.content.strip()
    match = re.search(r"\[[\d,\s]+\]", raw)
    if not match:
        return derived
    indices = json.loads(match.group())
    return [derived[i - 1] for i in indices if 1 <= i <= len(derived)]


def generate_proof(statements_path: Path) -> None:
    """Read a *_statements.json file and write a clean proof to *_final_proof.txt."""
    data = json.loads(statements_path.read_text(encoding="utf-8"))

    goal = None
    definitions: list[dict] = []
    given_facts: list[dict] = []
    derived: list[dict] = []

    for entry in data:
        t = entry.get("type", "fact")
        is_derived = entry.get("comment") == "Derived"
        if t == "goal":
            goal = entry
        elif t == "definition":
            definitions.append(entry)
        elif is_derived:
            derived.append(entry)
        else:
            given_facts.append(entry)

    if goal and derived:
        print(f"Filtering {len(derived)} derived statements with agent...")
        derived = _filter_statements(goal["statement"], derived)
        print(f"Kept {len(derived)} statements.")

    lines: list[str] = []

    # Header
    if goal:
        lines.append("THEOREM")
        lines.append("=" * 70)
        lines.append(goal["statement"])
        if goal.get("comment"):
            lines.append(f"({goal['comment']})")
        lines.append("")

    # Setup
    if definitions or given_facts:
        lines.append("SETUP")
        lines.append("-" * 70)
        for d in definitions:
            lines.append(f"  {d['statement']}")
        for f in given_facts:
            lines.append(f"  [{f['type'].upper()}] {f['statement']}")
        lines.append("")

    # Proof steps
    lines.append("PROOF")
    lines.append("-" * 70)
    for i, entry in enumerate(derived, start=1):
        lines.append(f"Step {i}. {entry['statement']}")
        if entry.get("proof"):
            lines.append("")
            lines.append(f"  Proof: {entry['proof']}")
        lines.append("")

    lines.append("QED")

    out_path = statements_path.parent / (statements_path.stem.removesuffix("_statements") + "_final_proof.txt")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Proof written to {out_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python -m src.proof_cleanup <path_to_statements.json>")
        sys.exit(1)
    generate_proof(Path(sys.argv[1]))
