"""Run without installing: python snapshot.py --disease ..."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from disease_snapshot.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
