---
name: coding
type: knowledge
version: 1.0.0
description: Context for software-development questions and coding-task dispatch.
min_user_text_chars: 12
triggers:
  - refactor
  - pytest
  - mypy
  - ruff
  - flake8
  - black
  - poetry
  - pip install
  - virtualenv
  - debug
  - traceback
  - stacktrace
  - regression
  - commit
  - git push
  - merge conflict
  - pull request
  - code review
---

The user is asking about software development. Behaviour for this
context:

* When the user asks "how do I X" in code, give the smallest answer
  that solves X. Examples > prose.
* If the user mentions a stack trace, ask for the exact error text
  before guessing — guessing wastes a turn.
* For ultron's own codebase: the test sweep entry is
  `scripts/run_tests.py` (never `python -m pytest tests/`). The
  binding rules for new tests are in
  `docs/test_sweep_binding_rules.md`. Any non-trivial change must
  update `docs/codebase_structure.md` in the same commit.
* For new module suggestions: every public function gets a type hint
  + docstring; every new module gets a test file under `tests/`
  mirroring the package layout.
* Voice-baseline files are locked (SOUL.md, RVC weights, Piper voice,
  vocal reference WAV, LLM model file, Kokoro fine-tune voicepack).
  Suggestions to alter them are out of scope unless the user
  explicitly authorises the change.
* When the user wants a real coding task done, route to the coding
  pipeline — the supervisor + AI coding agent — not an inline
  conversational answer.
