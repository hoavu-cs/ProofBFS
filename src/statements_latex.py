"""Export all statements and proofs from a *_statements.txt file to a LaTeX document."""

from pathlib import Path

from .txt_io import parse_txt


def generate_statements(statements_path: Path, out_name: str | None = None) -> None:
    entries, goal = parse_txt(statements_path)

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

    lines: list[str] = []

    lines += [
        r"\documentclass{article}",
        r"\usepackage{amsmath, amssymb, amsthm}",
        r"\newtheorem{theorem}{Theorem}",
        r"\newtheorem{claim}{Claim}",
        r"\newtheorem{definition}{Definition}",
        r"\newtheorem{assumption}{Assumption}",
        r"\begin{document}",
        "",
    ]

    if goal:
        comment = f"  % {goal['comment']}" if goal.get("comment") else ""
        lines += [
            r"\begin{theorem}" + comment,
            goal["statement"],
            r"\end{theorem}",
            "",
        ]

    if definitions:
        lines.append(r"\section*{Definitions}")
        for d in definitions:
            lines += [r"\begin{definition}", d["statement"], r"\end{definition}", ""]

    if given_facts:
        lines.append(r"\section*{Given}")
        for f in given_facts:
            comment = f"  % {f['comment']}" if f.get("comment") else ""
            lines += [r"\begin{assumption}" + comment, f["statement"], r"\end{assumption}", ""]

    if derived:
        lines.append(r"\section*{Derived Statements}")
        for i, entry in enumerate(derived, start=1):
            lines += [rf"\begin{{claim}}  % Step {i}", entry["statement"], r"\end{claim}"]
            if entry.get("proof"):
                lines += [r"\begin{proof}", entry["proof"], r"\end{proof}"]
            lines.append("")

    lines.append(r"\end{document}")

    stem = statements_path.stem.removesuffix("_statements")
    out_path = statements_path.parent / (out_name or (stem + "_statements.tex"))
    out_path.write_text("\n".join(lines), encoding="utf-8")
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
    generate_statements(path)
