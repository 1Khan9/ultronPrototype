# Kenning skills

Trigger-loaded knowledge bundles that inject capability-specific context into
the system prompt only when the user's message matches a trigger. Pattern
lineage attributed in `THIRD_PARTY_NOTICES.md`.

Each `.md` file is a skill. The leading YAML frontmatter declares:

* `name` — stable identifier (required).
* `type` — `knowledge` / `task` / `always_on` (optional; inferred from
  trigger presence).
* `triggers` — list of keywords OR `/slash-commands`. Any slash-prefixed
  trigger flips the whole list to slash-command semantics. Omit
  `triggers` entirely to mark the skill as always-on.
* `description` — short human-readable summary (optional, surfaced by
  `kenning diag skills`).
* `min_user_text_chars` — keyword-trigger guard floor (defaults to 8
  globally) — prevents false fires on one-word interjections.

The body is plain markdown — it's appended directly to the system
prompt when the skill fires. Keep skills short (target 100–800 tokens
each) so multi-skill matches don't blow the context budget.

Sources merge in precedence order (later wins on duplicate name):

1. `skills/` at the project root (public — this directory).
2. `~/.kenning/skills/` (user-level).
3. `<project>/.kenning/skills/` (per-project).

Disable individual skills via `skills.disabled` in `config.yaml`.
