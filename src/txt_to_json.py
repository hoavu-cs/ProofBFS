"""Convert an input.txt seed file to input.json.

Format of input.txt:
  # optional comment (applies to the next fact)
  type: statement

Usage:
  python -m src.txt_to_json <input.txt>
"""

import json
import sys
from pathlib import Path


def convert(txt_path: Path) -> Path:
    entries = []
    pending_comment: str | None = None

    for line in txt_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            pending_comment = line[1:].strip()
            continue
        kind, _, statement = line.partition(":")
        entry: dict = {
            "type": kind.strip(),
            "statement": statement.strip(),
            "proof": None,
            "comment": pending_comment,
        }
        entries.append(entry)
        pending_comment = None

    out_path = txt_path.with_suffix(".json")
    out_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False))
    print(f"Written to {out_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.txt_to_json <input.txt>")
        sys.exit(1)
    convert(Path(sys.argv[1]))
