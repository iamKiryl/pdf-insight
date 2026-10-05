"""Offline evaluation of live analysis results (no model calls in this package's checks)."""

import pathlib
import sys

# The backend is not an installed package (pywrangler vendors src/ for the Worker); make
# ``pdf_insight`` importable when the evaluation tools run via ``uv run python -m evaluation...``.
_SRC = str(pathlib.Path(__file__).resolve().parents[1] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
