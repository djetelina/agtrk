# Mid-conversation session registration nudge

## Context

The session registration gate only fires at conversation start (via hook). When a
completed session is followed by a new topic that turns into real work (code changes,
investigations), the work goes untracked. There's no enforcement mechanism
mid-conversation — only the agent's judgment.

## Decision

Added a soft nudge after the completion instructions:
"If you completed a session mid-conversation and a follow-up turns into new work
(code changes, investigations, or anything beyond a simple answer), register a new
session before proceeding."

## Tradeoff

This is a soft nudge, not a hard gate. The agent can still rationalize past it
("this is just a quick thing"). But going from zero nudge to some nudge shifts the
odds. No enforcement mechanism exists mid-conversation without fundamentally
changing how hooks work.

## Expectation

Some mid-conversation work will get tracked that previously wouldn't. Won't be
100% — watch for whether it catches anything at all. If it never triggers, the
nudge may need to be stronger or repositioned in the prompt.
