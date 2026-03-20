"""Shared I/O helpers for the ###-separated statement txt format."""

import re
from pathlib import Path


def parse_txt(txt_path: Path) -> tuple[list[dict], dict | None, list[str]]:
    """Parse a ###-separated text file.

    Block format (within each ### section):
        Type: statement text
        Proof: proof text        (optional, may be multi-line)
        Comment: comment text    (optional)

    Recognised special types:
        Goal:   the proof target (returned separately)
        Prompt: a hint or direction for the proof search (returned separately)

    Returns (entries, goal, prompts) where goal is the Goal block dict (or
    None), prompts is a list of prompt strings, and entries contains
    everything else.
    """
    entries = []
    goal: dict | None = None
    prompts: list[str] = []
    blocks = re.split(r"#{3,}", txt_path.read_text()) # split on "###"
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        
        lines = block.splitlines()
        kind, _, stmt = lines[0].partition(":")
        entry: dict = {
            "type": kind.strip(),
            "statement": stmt.strip(),
            "proof": None,
            "comment": None,
        }

        proof_lines: list[str] = []
        stmt_lines: list[str] = [stmt.strip()]
        in_proof = False
        in_statement = True

        for line in lines[1:]:
            s = line.strip()
            low = s.lower()
            if low.startswith("proof:"):
                in_proof = True
                in_statement = False
                proof_lines.append(s[6:].strip())
            elif low.startswith("comment:"):
                in_proof = False
                in_statement = False
                entry["comment"] = s[8:].strip() or None
            elif in_proof:
                proof_lines.append(s)
            elif in_statement:
                stmt_lines.append(line)  # preserve indentation for LaTeX

        entry["statement"] = "\n".join(stmt_lines).strip()

        if proof_lines:
            entry["proof"] = " ".join(l for l in proof_lines if l) or None

        if not (entry["type"] and entry["statement"]):
            continue

        if entry["type"].lower() == "goal":
            goal = entry
        elif entry["type"].lower() == "prompt":
            prompts.append(entry["statement"])
        else:
            entries.append(entry)

    return entries, goal, prompts
