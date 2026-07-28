from __future__ import annotations

import os
from pathlib import Path
import sys


if getattr(sys, "frozen", False):
    os.chdir(Path(sys.executable).resolve().parent)

from mil1553_fuzz.gui import main


if __name__ == "__main__":
    main()
