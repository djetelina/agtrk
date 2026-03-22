# Todo-selection exception to inject gate

## Context

The inject prompt's initial gate blocks the agent from asking any questions
before completing registration (register + heartbeat cron). When a user starts a
conversation wanting to pick up one of their existing todo items, the agent can't
ask "which one?" — it's forced to register blindly first, defeating the purpose
of the backlog workflow.

## Decision

Added an exception clause to the gate that allows the agent to present todo
sessions and let the user choose before completing registration. Once the user
picks a session, the agent proceeds with the normal "Resuming existing work"
path.

## Tradeoff

Slightly weakens the gate's absoluteness. An agent could misinterpret a message
as todo-selection when it isn't. Kept the trigger narrow (specific example
phrases) to reduce false positives.

## Expectation

Agents should present `agtrk list` output (or filtered todos) when a user
signals backlog intent, wait for the user to choose, then resume that session.
Watch for agents using this exception as a loophole to ask unrelated questions
before registering.
