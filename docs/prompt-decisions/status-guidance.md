# Status guidance in register instruction

## Context

Agents defaulted to `implementing` when registering because the prompt listed
statuses without explaining when to use each. An agent doing research/investigation
would pick `implementing` simply because it felt most "active."

## Decision

Added inline hint after the status options:
`(todo = noted for later; planning = researching/investigating; implementing = actively writing code)`

## Tradeoff

~15 tokens per session. Alternatives considered:
- Renaming statuses (e.g. `investigating`) — the name wasn't the problem, lack of guidance was
- Defaulting to `planning` — status would be wrong until the next 30-min cron heartbeat
- Removing status from register — loses ability to register backlog (`todo`) items

## Expectation

Agents should pick `planning` for research/investigation tasks and `implementing`
only when they're about to write code. Watch for: agents still defaulting to
`implementing` regardless, which would mean the hint is too subtle.
