"""Run ruff lint + mypy type check on backend."""

import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"


def main() -> None:
    print("=== ruff check ===")
    r1 = subprocess.run([sys.executable, "-m", "ruff", "check", "."], cwd=BACKEND_DIR)

    print("=== mypy ===")
    r2 = subprocess.run([sys.executable, "-m", "mypy", "src/"], cwd=BACKEND_DIR)

    sys.exit(r1.returncode or r2.returncode)


if __name__ == "__main__":
    main()
