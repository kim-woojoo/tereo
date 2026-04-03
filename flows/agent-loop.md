# Agent Loop

One main agent decides.
Subagents bring back receipts.
TEREO keeps the room honest.

Example pattern:

1. main agent freezes the promise, scope, and check
2. subagent makes one small change
3. subagent runs `tereo prove`, then returns `tereo show` or `tereo comment`
4. main agent keeps only the change with readable proof

If a subagent finds a new failure that makes the current win false,
that failure stays in the same loop.
Only side problems that do not make the receipt false move to the next promise.

TEREO works best when agents stop arguing from plausibility
and start returning measured evidence.
