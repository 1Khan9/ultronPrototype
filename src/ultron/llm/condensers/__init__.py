"""History compression strategies as a swappable :class:`Condenser` slot.

Pattern lineage attributed in ``THIRD_PARTY_NOTICES.md``.

The OpenHands SDK exposes a ``Condenser`` ABC that the orchestrator owns;
every LLM call goes through ``condenser.condense(history)`` so the
literal context the model sees is never assembled by hand. Five
strategies port here:

* :class:`NoOpCondenser` -- passthrough; useful for greetings + when
  history fits comfortably.
* :class:`RecentCondenser` -- keep the first ``keep_first`` turns +
  the last ``max_events - keep_first`` turns; drop the middle.
* :class:`AmortizedCondenser` -- intelligent forgetting without an
  LLM call; the catalog's "decision boundary" variant.
* :class:`ObservationMaskingCondenser` -- keep the event structure but
  blank tool / observation content older than ``attention_window``.
* :class:`LLMSummarizingCondenser` -- the heavy variant; once history
  exceeds ``max_size`` fire a side LLM call to summarise the dropped
  middle into one synthesised turn.

The closed-window file-view processor from the SWE-Agent catalog T2 is
intentionally kept in :mod:`ultron.llm.history_processors` -- it's
specialised to the bash_only file-view shape and not a general history
compressor.

Selection: :func:`build_condenser` reads
``llm.condenser.kind`` from config and returns the configured concrete.
:func:`select_condenser_for_intent` is the adaptive switcher (NoOp for
greetings, Recent for voice turns, LLMSummarizing for coding sessions).
"""

from ultron.llm.condensers.base import (
    Condenser,
    CondenserError,
    CondenseResult,
    Turn,
    char_count_tokens_for_turns,
    turn_text,
)
from ultron.llm.condensers.noop import NoOpCondenser
from ultron.llm.condensers.recent import RecentCondenser
from ultron.llm.condensers.amortized import AmortizedCondenser
from ultron.llm.condensers.observation_masking import (
    DEFAULT_MASK_TEMPLATE,
    ObservationMaskingCondenser,
)
from ultron.llm.condensers.llm_summarizing import LLMSummarizingCondenser
from ultron.llm.condensers.factory import (
    DEFAULT_CONDENSER_KIND,
    KNOWN_CONDENSER_KINDS,
    build_condenser,
    select_condenser_for_intent,
)

__all__ = [
    "AmortizedCondenser",
    "Condenser",
    "CondenseResult",
    "CondenserError",
    "DEFAULT_CONDENSER_KIND",
    "DEFAULT_MASK_TEMPLATE",
    "KNOWN_CONDENSER_KINDS",
    "LLMSummarizingCondenser",
    "NoOpCondenser",
    "ObservationMaskingCondenser",
    "RecentCondenser",
    "Turn",
    "build_condenser",
    "char_count_tokens_for_turns",
    "select_condenser_for_intent",
    "turn_text",
]
