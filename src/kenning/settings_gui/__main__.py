"""``python -m kenning.settings_gui`` -- run the control panel."""

from __future__ import annotations

import sys

from kenning.settings_gui.app import main

if __name__ == "__main__":
    sys.exit(main())
