import sys
from pathlib import Path

from src.app import run

if __name__ == "__main__":
    path = Path(input("Input JSON path: ").strip())
    if not path.exists():
        print(f"Error: {path} not found.")
        sys.exit(1)
    run(path)
