import os
import sys
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)
sys.path.insert(0, r"C:\Users\manni\Almond1.0\src")
sys.argv = ["almond", "desktop"]
from almond_ai.cli import main
main()
