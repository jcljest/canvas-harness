---
id: ADR-0003
status: accepted
date: 2026-10-06
affected_modules:
  - harness
supersedes: null
superseded_by: null
---

# ADR-0003: Course nicknames, resolved by the CLI

## Context

Teachers refer to classes by informal names ("AP", "AP2", "my physics kids",
"3rd period"), not by a tool alias or the official Canvas title. The posting
skill had nothing to map those names to courses, so it either asked every
time or left the match to Claude's judgment.

## Decision

- `courses.json` gains an optional `nicknames` list per course, collected by
  `/setup` ("What do you call this class?").
- Names are compared after removing case, spaces and punctuation.
- `load_roster` rejects a roster where any name (alias, nickname or exact
  title) would point to two courses.
- `canvas-harness which NAME` does the lookup deterministically: exact (normalized)
  matches only. With no match it exits 1 and lists close candidates. It never guesses.
- The `canvas-post` skill must use `which`. When nothing matches it asks the
  user and offers to save their words as a new nickname.

## Options Considered

- Fuzzy matching (closest name wins): fewer questions, but it can silently
  pick the wrong one of two similar courses (Physics vs AP Physics).
  Rejected; near matches are only suggested.
- Leaving it to the skill text: not testable. Rejected.

## Consequences

- An overlapping nickname is a setup error to fix, not something resolved at
  posting time.
- Near overlaps (e.g. "Physics" vs "AP Physics") are allowed but flagged by
  `/setup`, which asks the user to decide.
