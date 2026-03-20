import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from .txt_io import parse_txt

load_dotenv()

_client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)

LATEX_SYSTEM = """\
You are a LaTeX typesetter for mathematical proofs. Convert the given proof into a complete, compilable LaTeX document.
Rules:
- Use proper LaTeX math: \\frac{}{}, \\sqrt{}, \\sum, \\geq, \\leq, \\cdot, \\in, etc.
- Wrap inline math in $...$ and display math in \\[...\\] or align environments.
- The preamble MUST include exactly:
    \\usepackage{amsmath, amssymb, amsthm}
    \\newtheorem{theorem}{Theorem}
    \\newtheorem{claim}{Claim}
- Put the main goal inside \\begin{theorem}...\\end{theorem}.
- Put each intermediate proof step inside \\begin{claim}...\\end{claim} followed by \\begin{proof}...\\end{proof}.
- Keep the document minimal: \\documentclass{article} with the packages above only.
- Output ONLY the raw LaTeX document, no commentary, no markdown fences."""

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
    """Read a *_statements.txt file and write a LaTeX proof to *_final_proof.tex."""
    entries, goal, _ = parse_txt(statements_path)

    definitions: list[dict] = []
    given_facts: list[dict] = []
    derived: list[dict] = []

    for entry in entries:
        t = entry.get("type", "fact").lower()
        if entry.get("comment") == "Derived":
            derived.append(entry)
        elif t == "definition":
            definitions.append(entry)
        else:
            given_facts.append(entry)

    if goal and derived:
        print(f"Filtering {len(derived)} derived statements with agent...")
        derived = _filter_statements(goal["statement"], derived)
        print(f"Kept {len(derived)} statements.")

    stem = statements_path.stem.removesuffix("_statements")
    _write_latex(statements_path.parent / (stem + "_final_proof.tex"), goal, definitions, given_facts, derived)


def _write_latex(out_path: Path, goal: dict | None, definitions: list[dict], given_facts: list[dict], derived: list[dict]) -> None:
    sections: list[str] = []

    if goal:
        sections.append(f"THEOREM: {goal['statement']}")
        if goal.get("comment"):
            sections.append(f"({goal['comment']})")

    if definitions or given_facts:
        sections.append("\nSETUP:")
        for d in definitions:
            sections.append(f"- {d['statement']}")
        for f in given_facts:
            sections.append(f"- [{f['type'].upper()}] {f['statement']}")

    sections.append("\nPROOF STEPS:")
    for i, entry in enumerate(derived, start=1):
        sections.append(f"Step {i}. {entry['statement']}")
        if entry.get("proof"):
            sections.append(f"  Proof: {entry['proof']}")

    prompt = "\n".join(sections)
    print("Asking agent to format LaTeX...")
    response = _client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": LATEX_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    latex = response.choices[0].message.content.strip()
    # Strip markdown fences if the model added them anyway
    latex = re.sub(r"^```(?:latex)?\n?", "", latex)
    latex = re.sub(r"\n?```$", "", latex)

    out_path.write_text(latex, encoding="utf-8")
    print(f"LaTeX written to {out_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        path = Path(sys.argv[1])
    else:
        raw = input("Statements TXT path: ").strip()
        if not raw:
            print("Path cannot be empty.")
            sys.exit(1)
        path = Path(raw)
    generate_proof(path)