import os
import sys

# Modules under test live at the repo root, one level above this tests/ dir.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
