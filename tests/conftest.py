from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
# Keep tests independent of editable installs by adding local src/ directly.
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
