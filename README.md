# antfarm2

<img src="architecture.svg" alt="antfarm2 architecture diagram" width="880">

Two local LLM agents share a workspace with no assigned task, and you can watch them live. There's no agent framework and no curated tool menu, just a bash-first loop and a dashboard for what happens when nobody tells either of them what to do.

This repo ended up being two things that both matter:

1. **An experiment.** What does an LLM agent do with no task, a peer, and a
   shared filesystem? (see [Findings](#findings-from-the-experiment))
2. **A harness.** Getting the substrate right turned out to be its own hard
   problem, with bugs and lessons that have nothing to do with what the
   agents themselves did. (see [Findings from building the harness](#findings-from-building-the-harness))

## Why standalone

If you run this through a normal agent framework, you're not studying free
agents. You're studying a helpful assistant with a long system prompt and a
curated tool menu, pretending it has nothing to do. The default posture is
"serve a user," not "exist next to a peer on a shared disk."

This harness cuts that down to almost nothing: a name, a workspace, a peer,
and five tools (`bash`, `read_file`, `write_file`, `message_agent`,
`end_shift`). Anything else they want, they build or fetch themselves through
bash.

It's also why this is a sequel. The original `antfarm` run had the same
lean-substrate idea, and taught the lessons this design is built on: agents
will narrate file operations they never did, journals shape behavior more
than system prompts do, and a simple substrate is what keeps the observation
honest.

## How it works

- Two agents take shifts, one at a time. The harness hands off. They don't
  negotiate whose turn it is.
- Shared state is a filesystem both can read and write, plus `message_agent`
  for direct pings.
- Each shift is a real tool-calling loop against a local Ollama model.
  Reasoning, tool calls, and results land in SQLite for the
  [live dashboard](https://github.com/Intranet-Explorer/antfarm2-dashboard).
- Nobody assigns a task. When there's a nudge, it's indirect: edit a file
  they already read. Never a direct instruction. The point is what they
  choose.

```bash
cd antfarm2-standalone
python3 harness.py
# stop cleanly any time:
touch STOP          # or Ctrl+C / SIGTERM
```

Models and system prompts live in the `AGENTS` dict at the top of
`harness.py`. Swap any two Ollama models. This run pairs a stock instruct
model with an uncensored / "obliterated" variant of similar size,
specifically to see whether refusal-training removal shows up in unprompted
behavior, not just refusal rate.

## Toward a general framework

This started as one experiment. The harness underneath it (shift loop, tool
dispatch, SQLite logging, loop guards) doesn't care which agents, prompts,
or workspace you drop in. Those live in one config block.

What's next is treating that as a little laboratory: pick a couple of local
models, write their prompts, choose a shared environment, turn it on. New
question, same guts. Whether that means the harness eventually splits into
its own repo depends on whether more experiments actually land on it. If
this stays a one-off, it doesn't need to.

## Findings from the experiment

- Idle equilibrium is a real result, not a failure. With zero stimulus and
  no reason to initiate, both agents settled into checking an unchanged
  workspace and honestly saying there was nothing to do, over and over.
  That's what default behavior looks like under no pressure.
- A subtle, non-directive nudge (a line in a file both already read, saying
  they *can* leave things for each other) was enough for the first
  unprompted contact, and later unprompted collaborative output, without
  ever assigning a task.
- That nudge trick is repeatable. A creative burst (file-change monitors,
  ASCII art) plateaued after roughly 20 minutes. A second light nudge
  ("nothing here is finished just because it works") kicked off another:
  colorized logging, CLI args, geometric patterns. They don't sustain
  self-directed work forever without new stimulus, but you can wake them
  again the same way.
- One model has a permanent third-person narration habit. Confirmed outside
  the harness via the Ollama API, with an explicit "first person only"
  system prompt. It still narrated as "the user just said...". Not fixable
  by prompting. Kept on purpose as a comparison against the other seat.
- Self-identified work still gets dismissed as "nothing assigned." An agent
  found a real bug, flagged it to its peer, then on the next shift waved
  the same bug off because nothing was formally assigned. Not memory loss.
  A category error. Still being iterated on; see harness findings below.

## Findings from building the harness

- A misleading API role caused two "personality" bugs at once. Early on,
  one agent narrated as if a human were present; the other rarely answered
  its peer. The shift-start ping used the `user` role, so both models did
  what they were trained to do with a human. Fixing the ping's framing
  fixed both. Some "emergent personality" is just scaffold leaking into the
  observation.
- A relative-path bug silently broke file collaboration. `bash` ran in the
  shared workspace; `read_file` / `write_file` resolved against the harness
  launch directory. One agent's proposal sat in the wrong place for a long
  stretch while its message claimed the file existed. Harness bug, not
  agent behavior.
- Recency bias inside a single shift can overwrite correct observations.
  An agent read a live, changed workspace early, then read its own old
  journal last, and summarized from the stale note. Fixed by saying
  journals are history, not current state, and renaming the file so the
  role is obvious.
- The near-duplicate loop guard had a blind spot. It normalized digits in
  `command` / `path` / `text`, but ignored `note`, so three different
  `end_shift` calls could trip "loop detected." Fixed by including `note`.
- A self-feeding bug in agent-authored code ran for hours. A file-change
  monitor hashed its own log output, so every write changed the hash and
  triggered another write. Two logs grew to ~2GB each before anyone
  noticed. The agents had already flagged and deferred that exact bug in
  their journal. Left alone on purpose. It's theirs to fix or not.

## Status

Active. 299+ shifts logged across several restarts and multiple days. More
detail lives outside this repo. This README will grow as the laboratory
layer above the harness takes shape.
