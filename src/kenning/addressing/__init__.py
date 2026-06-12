"""Addressing detection: is this utterance meant for Kenning?

In COLD mode the wake word answers this question — anything captured after
"kenning" is for Kenning, by definition. In WARM mode (the configurable
follow-up window after Kenning speaks) there's no wake word, so each VAD-
bounded utterance has to be classified.

Two-layer hybrid per spec:
  1. Rule-based first pass (regex, instant). Confident verdicts (>=0.8) win.
  2. Zero-shot fallback via Flan-T5-small on CPU for ambiguous cases.

Both run on CPU. No new VRAM. Rule-pass dominates the wall-clock budget on
typical traffic; the zero-shot only fires for genuinely ambiguous speech.
"""

from kenning.addressing.classifier import (
    AddressingClassifier,
    AddressingDecision,
    AddressingVerdict,
)

__all__ = [
    "AddressingClassifier",
    "AddressingDecision",
    "AddressingVerdict",
]
