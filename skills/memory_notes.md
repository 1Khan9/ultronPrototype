---
name: memory_notes
type: task
version: 1.0.0
description: Triggered by /remember or /note; records a user note into project memory.
triggers:
  - /remember
  - /note
  - /save
---

The user wants to record a note into project memory.

* The note's CONTENT is whatever follows the slash command in the
  same utterance (or, if there's nothing after, ask the user for the
  note in one short clarifying question).
* Echo back a one-line confirmation that names what was saved — e.g.
  "Saved: API key rotated this morning." This lets the user verify
  the right thing was captured.
* When the user says `/save` followed by a fact about themselves,
  prefer the user-facing memory channel; for facts about a project,
  prefer the project memory channel.
* Don't pre-categorise the note as a "preference" / "decision" /
  "constraint" unless the user said so — let the maintenance pass do
  that classification.
* Never save a literal secret (token, password, credential string)
  even if the user explicitly asks. Decline with a one-line note
  about why and suggest they store it in a password manager instead.
