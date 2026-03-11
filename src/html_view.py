"""Generates a MathJax-rendered HTML view from a *_statements.json file."""
import html
import json
import re
from pathlib import Path

_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ProofBFS — {title}</title>
<script>
    window.MathJax = {{
        tex: {{
            inlineMath: [['$','$'], ['\\(','\\)']],
            displayMath: [['$$','$$'], ['\\[','\\]']]
        }}
    }};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js" async></script>
<style>
  body {{ font-family: Georgia, serif; max-width: 860px; margin: 40px auto; padding: 0 20px; line-height: 1.7; color: #222; }}
  h1 {{ font-size: 1.4em; border-bottom: 2px solid #333; padding-bottom: 6px; }}
  h2 {{ font-size: 1.1em; margin-top: 2em; color: #444; }}
  .goal {{ background: #fffbe6; border-left: 4px solid #f0b429; padding: 10px 16px; margin: 1em 0; border-radius: 4px; }}
  .card {{ border: 1px solid #ddd; border-radius: 6px; padding: 12px 16px; margin: 10px 0; }}
  .card.derived {{ border-left: 4px solid #4caf50; }}
  .badge {{ display: inline-block; font-size: 0.75em; padding: 2px 8px; border-radius: 10px;
            font-family: monospace; margin-right: 6px; background: #eee; color: #555; }}
  .proof {{ margin-top: 8px; color: #444; font-size: 0.95em; }}
  .proof-label {{ font-weight: bold; color: #333; }}
</style>
</head>
<body>
<h1>∴ ProofBFS — {title}</h1>
{goal_block}
<h2>Given</h2>
{given_blocks}
<h2>Derived</h2>
{derived_blocks}
</body>
</html>"""


def generate_html(derived_path: Path) -> None:
    data = json.loads(derived_path.read_text(encoding="utf-8"))
    goal_block = ""
    given_html: list[str] = []
    derived_html: list[str] = []

    def _normalize_math_delimiters(text: str) -> str:
        return (
            text.replace("\\[", "$$")
            .replace("\\]", "$$")
            .replace("\\(", "$")
            .replace("\\)", "$")
        )

    def _render_text(text: str) -> str:
        text = _normalize_math_delimiters(text)
        # Escape HTML only outside math delimiters so MathJax receives raw LaTeX.
        parts = re.split(r'(\$\$[\s\S]*?\$\$|\$[^$\n]*?\$)', text)
        result = "".join(
            p if p.startswith("$") else html.escape(p).replace("\n", "<br>")
            for p in parts
        )
        return result

    def _card(entry: dict, derived: bool = False) -> str:
        badge = f'<span class="badge">{entry.get("type", "fact")}</span>'
        stmt = _render_text(entry["statement"])
        proof = entry.get("proof") or ""
        proof_html = (
            f'<div class="proof"><span class="proof-label">Proof:</span> {_render_text(proof)}</div>'
            if proof else ""
        )
        cls = "card derived" if derived else "card"
        return f'<div class="{cls}">{badge}{stmt}{proof_html}</div>'

    for entry in data:
        t = entry.get("type", "fact")
        is_derived = entry.get("comment") == "Derived"
        if t == "goal":
            goal_block = f'<div class="goal"><strong>Goal:</strong> {_render_text(entry["statement"])}</div>'
        elif is_derived:
            derived_html.append(_card(entry, derived=True))
        else:
            given_html.append(_card(entry))

    title = derived_path.stem.removesuffix("_statements")
    page_html = _TEMPLATE.format(
        title=title,
        goal_block=goal_block,
        given_blocks="\n".join(given_html) or "<p><em>None.</em></p>",
        derived_blocks="\n".join(derived_html) or "<p><em>None yet.</em></p>",
    )
    out = derived_path.parent / (title + "_view.html")
    out.write_text(page_html, encoding="utf-8")
