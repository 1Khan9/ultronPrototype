"""Regression test for ``EmbeddingBackend.embed`` -- the PUBLIC per-text embed the
orchestrator injects as the Twitch addressing residual tie-breaker (``embed_fn``).

Bug (2026-06-27): the orchestrator wired ``embed_fn = lambda t: (_eb.embed([t]) or
[None])[0]`` but ``EmbeddingBackend`` only had a private ``_embed``. So every Twitch
chat-addressing call raised ``'EmbeddingBackend' object has no attribute 'embed'``
(logged ~once per message) and addressing fell back to its lexical-only path. Fix =
add the public ``embed`` method these tests pin.
"""
import numpy as np
import pytest

from kenning.audio._router_backends import EmbeddingBackend


def _backend_with_canned(vectors):
    """An EmbeddingBackend whose HTTP round-trip is replaced by a canned response,
    so the real ``_embed`` -> ``embed`` path runs with no sidecar."""
    eb = EmbeddingBackend()
    eb._post = lambda path, payload, timeout=None: {"vectors": vectors}  # type: ignore[method-assign]
    return eb


def test_embed_method_exists_and_is_callable():
    # Guards the AttributeError regression directly.
    assert callable(getattr(EmbeddingBackend, "embed", None))


def test_embed_returns_one_l2normalized_vector_per_text():
    eb = _backend_with_canned([[3.0, 4.0]])
    out = eb.embed(["hello team"])
    assert isinstance(out, list) and len(out) == 1
    assert pytest.approx(float(np.linalg.norm(out[0])), abs=1e-5) == 1.0  # unit length


def test_embed_empty_texts_is_empty_list():
    eb = _backend_with_canned([])
    assert eb.embed([]) == []


def test_orchestrator_embed_fn_pattern_returns_a_vector():
    # The EXACT wiring in orchestrator.py: (_eb.embed([t]) or [None])[0]
    eb = _backend_with_canned([[1.0, 0.0, 0.0]])
    embed_fn = lambda t: (eb.embed([t]) or [None])[0]  # noqa: E731
    vec = embed_fn("is ultron a bot")
    assert vec is not None
    assert pytest.approx(float(np.linalg.norm(vec)), abs=1e-5) == 1.0
