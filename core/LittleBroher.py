"""Compatibility launcher for the former duplicate executable."""
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from LittleBrother import main
    raise SystemExit(main())
