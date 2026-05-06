"""Local LLM inference via llama-cpp-python.

The Ultron system prompt is baked in at construction. Conversation history is
kept as a list of (role, content) turns; the most recent N pairs are included
in each prompt, with older turns dropped to stay within the context window.
"""

from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from threading import Event
from typing import Deque, Iterator, Optional, Tuple

from config import settings
from ultron.utils.logging import get_logger

logger = get_logger("llm.inference")

Turn = Tuple[str, str]  # (role, content)


class LLMEngine:
    """Wraps a llama-cpp-python ``Llama`` instance with chat history.

    Args:
        model_path: Path to a GGUF file.
        n_ctx: Context window in tokens.
        n_gpu_layers: -1 for full offload to GPU, 0 for CPU-only.
        system_prompt: Persistent system message.
        history_turns: Max user/assistant turn pairs to retain.
    """

    def __init__(
        self,
        model_path: Path = settings.LLM_MODEL_PATH,
        n_ctx: int = settings.LLM_CONTEXT_LENGTH,
        n_gpu_layers: int = settings.LLM_GPU_LAYERS,
        system_prompt: str = settings.ULTRON_SYSTEM_PROMPT,
        history_turns: int = settings.LLM_HISTORY_TURNS,
    ) -> None:
        from llama_cpp import Llama

        if not Path(model_path).is_file():
            raise FileNotFoundError(
                f"LLM model not found at {model_path}. "
                f"Run `python scripts/download_models.py` first."
            )

        self.model_path = Path(model_path)
        self.system_prompt = system_prompt
        self.history_turns = history_turns
        self._history: Deque[Turn] = deque(maxlen=history_turns * 2)
        self._cancel = Event()

        logger.info("Loading LLM: %s (n_ctx=%d, n_gpu_layers=%d)…",
                    model_path, n_ctx, n_gpu_layers)
        t0 = time.monotonic()
        try:
            self._llm = Llama(
                model_path=str(model_path),
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
                verbose=False,
            )
        except Exception as e:
            logger.error("LLM load failed: %s", e)
            raise
        logger.info("LLM ready in %.2fs", time.monotonic() - t0)

    # --- context manager -----------------------------------------------------

    def __enter__(self) -> "LLMEngine":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._llm = None  # release GPU memory at GC time

    # --- history management --------------------------------------------------

    def reset_history(self) -> None:
        self._history.clear()

    def _build_messages(self, user_message: str) -> list[dict[str, str]]:
        msgs = [{"role": "system", "content": self.system_prompt}]
        for role, content in self._history:
            msgs.append({"role": role, "content": content})
        msgs.append({"role": "user", "content": user_message})
        return msgs

    # --- generation ----------------------------------------------------------

    def cancel(self) -> None:
        """Signal :meth:`generate_stream` to stop emitting tokens.

        The underlying llama-cpp call will continue until its current token
        finishes — but the iterator will exit immediately afterward.
        """
        self._cancel.set()

    def generate(self, user_message: str) -> str:
        """Blocking generation. Returns the full response string."""
        messages = self._build_messages(user_message)
        t0 = time.monotonic()
        out = self._llm.create_chat_completion(
            messages=messages,
            temperature=settings.LLM_TEMPERATURE,
            top_p=settings.LLM_TOP_P,
            max_tokens=settings.LLM_MAX_TOKENS,
            repeat_penalty=settings.LLM_REPEAT_PENALTY,
        )
        text = out["choices"][0]["message"]["content"].strip()
        logger.info(
            "LLM: %d chars in %.2fs (%d tokens)",
            len(text),
            time.monotonic() - t0,
            out.get("usage", {}).get("completion_tokens", -1),
        )
        self._history.append(("user", user_message))
        self._history.append(("assistant", text))
        return text

    def generate_stream(self, user_message: str) -> Iterator[str]:
        """Yield response tokens as they arrive.

        The full response is appended to history once the stream completes
        normally; on cancel, partial output is recorded so the model
        remembers what it had said.
        """
        self._cancel.clear()
        messages = self._build_messages(user_message)
        t0 = time.monotonic()
        first_token_time: Optional[float] = None
        accumulated: list[str] = []

        stream = self._llm.create_chat_completion(
            messages=messages,
            temperature=settings.LLM_TEMPERATURE,
            top_p=settings.LLM_TOP_P,
            max_tokens=settings.LLM_MAX_TOKENS,
            repeat_penalty=settings.LLM_REPEAT_PENALTY,
            stream=True,
        )

        try:
            for chunk in stream:
                if self._cancel.is_set():
                    logger.info("LLM stream canceled by caller")
                    break
                delta = chunk["choices"][0].get("delta", {}).get("content")
                if not delta:
                    continue
                if first_token_time is None:
                    first_token_time = time.monotonic()
                    logger.info("LLM TTFT: %.0fms",
                                (first_token_time - t0) * 1000)
                accumulated.append(delta)
                yield delta
        finally:
            full = "".join(accumulated).strip()
            if full:
                self._history.append(("user", user_message))
                self._history.append(("assistant", full))
            logger.info(
                "LLM stream: %d chars in %.2fs",
                len(full),
                time.monotonic() - t0,
            )
