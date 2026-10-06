"""Giriş noktası:  python run.py <komut>   (ör. python run.py weekly)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qin.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
