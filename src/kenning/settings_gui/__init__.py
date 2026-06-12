"""Voice-launched settings GUI for Kenning.

A SEPARATE detached process (``python -m kenning.settings_gui``): the
voice loop spawns it and forgets it, so opening/closing the panel can
never affect the running pipeline -- closing it returns the system to
exactly the state it ran in before, with zero residual resources.

Modules:
    spec   -- the curated knob catalogue + comment-preserving
              ``config.yaml`` patcher (fully unit-tested, no UI).
    launch -- the strict voice matcher + spawn/close helpers the
              orchestrator delegates to.
    app    -- the tkinter dark-theme panel (settings cards + live log
              stream + Update/Close), UI layer only.
"""
