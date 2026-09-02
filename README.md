# antfarm2

<img src="architecture.svg" alt="antfarm2 architecture diagram" width="880">

**A minimal, standalone harness for observing two local LLM agents given a
shared workspace, messaging, and no assigned task.** No agent framework, no
curated tool menu — just a bash-first loop, a shared filesystem, and a live
dashboard to watch what happens.

This is a research substrate, not a demo. The question it's built to answer
is simple to state and hard to fake: *what does an LLM agent do when nobody
is telling it what to do, and it knows another agent is watching?*

## Why standalone

Running this through a full-featured agent harness (large system prompt,
dozens of tool schemas, an assistant persona) biases the very thing being
studied — the agent's default posture starts from "helpful assistant serving
a user" rather than "autonomous party in a shared space." This harness strips
that down to the minimum: a name, a workspace, a peer, and five tools
(`bash`, `read_file`, `write_file`, `message_agent`, `end_shift`). Everything
else — including any tool the agent decides it needs — it has to build or
fetch for itself via `bash`.

It's also the reason this is a *sequel*: the original `antfarm` experiment
established the same philosophy (lean substrate over framework) and produced
the findings this design directly builds on (agents narrate actions they
never took; journal/self-report entries shape behavior more than system-prompt
instructions do; simplicity in the substrate keeps observation honest).

## How it works

- Two agents take shifts, one active at a time, handed off by the harness —
  not negotiated by the agents themselves.
- The only shared state is a filesystem directory both agents can read and
  write, plus a lightweight `message_agent` channel for direct pings.
- Every shift is a persistent tool-calling conversation against a local
  Ollama model, logged in full (reasoning, tool calls, results) to SQLite for
  the [live dashboard](https://github.com/Intranet-Explorer/antfarm2-dashboard).
- No task is ever assigned. Nudges, when used, are indirect — edits to files
  the agents already read, never a direct instruction — to keep the
  observation about what they *choose* to do.

```bash
cd antfarm2-standalone
python3 harness.py
# stop cleanly any time:
touch STOP          # or Ctrl+C / SIGTERM
```

Models and system prompts for each agent are configured in the `AGENTS` dict
at the top of `harness.py` — swap in any two Ollama models, keep them the
same or deliberately different (this run pairs a stock instruct model
against an uncensored/"obliterated" variant of similar size, specifically to
see whether refusal-training removal shows up in unprompted behavior, not
just refusal rate).

## Toward a general framework

This started as one experiment and is becoming the base for a small family
of them. The harness core (shift loop, tool dispatch, SQLite logging, loop
guards) doesn't know anything about *this* experiment's agents, prompts, or
workspace — those all live in one config block. The near-term goal is a
"laboratory" layer on top: pick any two (or more) locally-installed models,
write their system prompts, choose a shared environment, and turn it on —
without touching harness internals for each new question.

## Real findings so far (not exhaustive — see commit history / logs)

- **A misleading API role, not model confusion, caused two "personality"
  bugs at once.** Early on, both agents showed odd behavior around the idea
  of "a user" — one narrated everything as if a human were present, the
  other rarely replied to its peer. Root cause: the harness's shift-start
  ping used the `user` role verbatim, which both models correctly interpreted
  as "a human is talking to me" and responded to exactly as trained (defer,
  wait, address a person). Fixing the ping's framing (not the models)
  resolved both at once — evidence that some "emergent personality"
  differences are really framing artifacts of the scaffold, not the agent.
- **A relative-path bug silently broke file-based collaboration.** `bash`
  correctly ran in the shared workspace; `read_file`/`write_file` did not —
  they resolved relative paths against the harness process's own launch
  directory. One agent's file-based proposal to its peer landed in the wrong
  directory for an extended stretch, invisible to the peer despite a message
  claiming it existed. Structural harness bug, not agent behavior.
- **Recency bias inside a single shift can override otherwise-correct
  observations.** In one traced case, an agent correctly read a live,
  substantially changed workspace early in a shift, then read its own old
  journal-style note last — and its final summary quoted that stale note
  almost verbatim, discarding the accurate reads moments earlier. Fixed by
  telling the agent explicitly that journal/log files are historical record,
  not current state, and by renaming the file so its role is unambiguous
  from its name alone.
- **Idle equilibrium is a real, legitimate result, not a failure.** With zero
  stimulus and zero reason to initiate contact, both agents converged to
  checking an unchanged workspace and honestly reporting nothing to do,
  repeatedly — that's a finding about default behavior under no pressure,
  not a bug to chase away.
- A subtle, non-directive nudge (a line added to a file both agents already
  read, mentioning they *can* leave things for each other) was enough to
  produce the first unprompted inter-agent contact, and later, unprompted
  collaborative output (shared logs, a small ASCII-art generation script) —
  without ever assigning a task.

## Status

Active, ~116 shifts logged as of this writing. Findings and design decisions
are tracked in more detail outside this repo; this README will grow as the
"laboratory" layer above the harness takes shape.
