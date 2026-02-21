"""Run backend tests."""

import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"


def main() -> None:
    subprocess.run(
        [sys.executable, "-m", "pytest", "-v", *sys.argv[1:]],
        cwd=BACKEND_DIR,
        check=True,
    )


if __name__ == "__main__":
    main()
