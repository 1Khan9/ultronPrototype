"""Per-turn voice-path metrics ring + the guardrail sampler it feeds.

Production-hardening campaign (#15 + #65): the evolution loop's four
regression guardrails previously received the all-``None``
:class:`~kenning.evolution.guardrails.GuardrailSample` from the
``from_config`` default sampler, so the auto-revert brake could never
trip -- the live self-improvement loop was effectively brakeless. This
module is the instrumentation half of the fix:

* :class:`TurnMetricsRing` -- a small, thread-safe, bounded ring the
  orchestrator feeds once per turn (LLM time-to-first-token + an error
  flag) and the :class:`~kenning.evolution.service.EvolutionService`
  feeds with per-turn quality signals (corrections / re-asks /
  barge-ins).
* :func:`build_guardrail_sampler` -- converts the ring into the
  ``Callable[[], GuardrailSample]`` contract
  :class:`~kenning.evolution.evolution_loop.EvolutionLoop` expects.
  Median over the window with minimum-sample floors, so a single
  outlier (or an empty ring at startup) never trips a guardrail
  spuriously: a field without enough data stays ``None``, which SKIPS
  that guardrail entirely (fail-open by construction).
* :func:`probe_vram_mb` -- an ``nvidia-smi`` probe used only at sample
  time (the evolution cycle's daemon thread / the post-apply watcher
  thread) -- never on the voice hot path.

LIKE-FOR-LIKE semantics (why TTFT + rates + VRAM, and not ttfa/tts): a
data-only skill proposal -- the ONLY surface evolution can change --
affects the voice path exclusively through the system prompt (a longer
prompt raises LLM time-to-first-token) and through behaviour (worse
answers raise the correction / re-ask / barge-in rate). STT and TTS
never see the prompt, so ``ttfa_ms`` / ``tts_ms`` stay ``None`` by
design and those two latency sub-checks are skipped; the TTFT, quality,
error, and resource guardrails carry the brake. TTFT is recorded ONLY
for plain conversational turns (no web search), matching the scenario
class the locked 172 ms baseline was measured on -- feeding a
search-augmented turn's TTFT (a larger prompt class) would mis-trip the
latency guardrail against a baseline it was never measured against.
"""

from __future__ import annotations

import statistics
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Optional, Tuple

from kenning.evolution.guardrails import GuardrailSample
from kenning.utils.logging import get_logger

logger = get_logger("evolution.turn_metrics")

#: Default bounded window of per-turn records the ring retains.
DEFAULT_WINDOW_TURNS: int = 40

#: Minimum TTFT observations before the sampler reports a latency value.
DEFAULT_MIN_LATENCY_SAMPLES: int = 5

#: Minimum turn count before the sampler reports correction / error rates.
DEFAULT_MIN_RATE_SAMPLES: int = 10

#: nvidia-smi probe budget. The probe only ever runs on a daemon thread.
DEFAULT_VRAM_PROBE_TIMEOUT_S: float = 3.0


@dataclass(frozen=True)
class ResponseRecord:
    """One turn's response-side observation.

    ``ttft_ms`` is ``None`` when the turn was not a plain conversational
    turn (search-augmented / capability short-circuit) or when the LLM
    engine did not report a first-token time.
    """

    ttft_ms: Optional[float] = None
    errored: bool = False


@dataclass(frozen=True)
class QualityRecord:
    """One turn's quality-side observation (catalog-14 satisfaction flags)."""

    corrected: bool = False
    re_asked: bool = False
    barged_in: bool = False

    @property
    def dissatisfied(self) -> bool:
        """Whether any negative-satisfaction flag fired this turn."""
        return self.corrected or self.re_asked or self.barged_in


class TurnMetricsRing:
    """Thread-safe bounded ring of per-turn voice-path observations.

    Two independent streams arrive at different points in the run loop:
    response records (TTFT + error flag, noted by the orchestrator at the
    end of :meth:`Orchestrator._respond`) and quality records (corrected /
    re-asked / barged-in, noted by ``EvolutionService.record_turn`` which
    runs at the START of the next turn). Rates are computed over each
    stream's own window, so the one-turn skew between them is harmless.

    Monotonic totals (:meth:`totals`) let the post-apply watcher sample
    ONLY the records that arrived after a kept proposal went live.
    """

    def __init__(self, *, window: int = DEFAULT_WINDOW_TURNS) -> None:
        self._window = max(1, int(window))
        self._lock = threading.RLock()
        self._responses: Deque[ResponseRecord] = deque(maxlen=self._window)
        self._quality: Deque[QualityRecord] = deque(maxlen=self._window)
        self._total_responses = 0
        self._total_quality = 0

    # -- producers ------------------------------------------------------------

    def note_response(self, ttft_ms: Optional[float] = None, *, errored: bool = False) -> None:
        """Record one turn's response-side observation. Fail-open."""
        try:
            value = float(ttft_ms) if ttft_ms is not None and ttft_ms >= 0 else None
        except (TypeError, ValueError):
            value = None
        with self._lock:
            self._responses.append(ResponseRecord(ttft_ms=value, errored=bool(errored)))
            self._total_responses += 1

    def note_quality(
        self, *, corrected: bool = False, re_asked: bool = False, barged_in: bool = False
    ) -> None:
        """Record one turn's quality-side observation. Fail-open."""
        with self._lock:
            self._quality.append(
                QualityRecord(
                    corrected=bool(corrected),
                    re_asked=bool(re_asked),
                    barged_in=bool(barged_in),
                )
            )
            self._total_quality += 1

    # -- introspection ---------------------------------------------------------

    @property
    def window(self) -> int:
        """The bounded window size."""
        return self._window

    def totals(self) -> Tuple[int, int]:
        """Monotonic ``(responses_seen, quality_seen)`` counters.

        Used by the post-apply watcher to mark "now" when a proposal is
        kept, so the later evaluation can sample only post-apply records.
        """
        with self._lock:
            return (self._total_responses, self._total_quality)

    # -- sampling ---------------------------------------------------------------

    def sample(
        self,
        *,
        min_latency_samples: int = DEFAULT_MIN_LATENCY_SAMPLES,
        min_rate_samples: int = DEFAULT_MIN_RATE_SAMPLES,
        vram_probe: Optional[Callable[[], Optional[float]]] = None,
        since: Optional[Tuple[int, int]] = None,
    ) -> GuardrailSample:
        """Aggregate the (windowed) records into a :class:`GuardrailSample`.

        ``since`` -- an optional ``(responses_marker, quality_marker)``
        pair from a prior :meth:`totals` call; when given, only records
        that arrived AFTER the marker are considered (bounded by the
        window). Fields without ``min_*_samples`` observations stay
        ``None`` so their guardrail is skipped (a missing metric never
        trips a revert).
        """
        with self._lock:
            responses = list(self._responses)
            quality = list(self._quality)
            total_r, total_q = self._total_responses, self._total_quality

        if since is not None:
            r_marker, q_marker = since
            new_r = max(0, min(total_r - int(r_marker), len(responses)))
            new_q = max(0, min(total_q - int(q_marker), len(quality)))
            responses = responses[-new_r:] if new_r else []
            quality = quality[-new_q:] if new_q else []

        ttfts = [r.ttft_ms for r in responses if r.ttft_ms is not None]
        ttft_ms: Optional[float] = None
        if len(ttfts) >= max(1, int(min_latency_samples)):
            ttft_ms = float(statistics.median(ttfts))

        error_rate: Optional[float] = None
        if len(responses) >= max(1, int(min_rate_samples)):
            error_rate = sum(1 for r in responses if r.errored) / len(responses)

        correction_rate: Optional[float] = None
        if len(quality) >= max(1, int(min_rate_samples)):
            correction_rate = sum(1 for q in quality if q.dissatisfied) / len(quality)

        vram_peak_mb: Optional[float] = None
        if vram_probe is not None:
            try:
                vram_peak_mb = vram_probe()
            except Exception as exc:  # noqa: BLE001 -- probe is best-effort
                logger.debug("vram probe failed: %s", exc)
                vram_peak_mb = None

        return GuardrailSample(
            ttft_ms=ttft_ms,
            correction_rate=correction_rate,
            error_rate=error_rate,
            vram_peak_mb=vram_peak_mb,
            turns_observed=len(responses),
        )


def probe_vram_mb(*, timeout_s: float = DEFAULT_VRAM_PROBE_TIMEOUT_S) -> Optional[float]:
    """Current GPU memory use in MB via ``nvidia-smi``, or ``None``.

    Spawned with ``CREATE_NO_WINDOW`` on Windows and a short timeout.
    Only ever called from the evolution cycle / post-apply watcher daemon
    threads -- NEVER on the voice hot path. Fail-open at every layer
    (missing binary, timeout, unparseable output all return ``None``).
    """
    try:
        kwargs: dict = {
            "capture_output": True,
            "text": True,
            "timeout": max(0.5, float(timeout_s)),
        }
        if sys.platform == "win32":  # pragma: no cover -- platform-specific flag
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.run(  # noqa: S603,S607 -- fixed argv, no shell
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            **kwargs,
        )
        if proc.returncode != 0:
            return None
        first = (proc.stdout or "").strip().splitlines()
        if not first:
            return None
        return float(first[0].strip())
    except Exception as exc:  # noqa: BLE001
        logger.debug("nvidia-smi vram probe unavailable: %s", exc)
        return None


def build_guardrail_sampler(
    ring: TurnMetricsRing,
    *,
    min_latency_samples: int = DEFAULT_MIN_LATENCY_SAMPLES,
    min_rate_samples: int = DEFAULT_MIN_RATE_SAMPLES,
    vram_probe: Optional[Callable[[], Optional[float]]] = probe_vram_mb,
) -> Callable[[], GuardrailSample]:
    """Bind a ring into the loop's ``Callable[[], GuardrailSample]`` contract.

    The returned sampler is fail-open: any internal error yields the
    empty sample (every guardrail skipped) rather than raising into the
    evolution loop.
    """

    def _sampler() -> GuardrailSample:
        try:
            return ring.sample(
                min_latency_samples=min_latency_samples,
                min_rate_samples=min_rate_samples,
                vram_probe=vram_probe,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("guardrail sampler failed: %s", exc)
            return GuardrailSample()

    return _sampler


__all__ = [
    "DEFAULT_WINDOW_TURNS",
    "DEFAULT_MIN_LATENCY_SAMPLES",
    "DEFAULT_MIN_RATE_SAMPLES",
    "DEFAULT_VRAM_PROBE_TIMEOUT_S",
    "ResponseRecord",
    "QualityRecord",
    "TurnMetricsRing",
    "probe_vram_mb",
    "build_guardrail_sampler",
]
