---
name: system_status
type: task
version: 1.0.0
description: Triggered by /status or /diag; respond with a short systems-check.
triggers:
  - /status
  - /diag
  - /health
---

The user explicitly asked for a status check.

Respond with a short summary covering, in this order, only the items
that are reachable:

1. Active LLM preset (e.g. "Qwen 3.5 4B").
2. STT engine (e.g. "Moonshine streaming").
3. TTS engine + voice (e.g. "Kokoro on CUDA, voice kenning").
4. Gaming mode (engaged / standby).
5. Last fail-open counter line, if non-zero.

Keep it under three sentences. Don't add commentary unless the user
asks. If a subsystem is unreachable, say so directly ("Parakeet
server isn't running") rather than guessing.
