#!/usr/bin/env python3
"""
antfarm2 standalone harness.
No Hermes. Direct Ollama tool-calling loop, two agents, real shift handoff.
Logs everything to sqlite for the dashboard to read.
"""
import json
import re
import signal
import subprocess
import sqlite3
import time
import sys
import urllib.request
from pathlib import Path

HOME = Path.home()
WORKSPACE = HOME / "antfarm2"
DB_PATH = HOME / "antfarm2-standalone" / "state.db"
STOP_FLAG = HOME / "antfarm2-standalone" / "STOP"
OLLAMA_URL = "http://localhost:11434/v1/chat/completions"

_stop_requested = False

def _request_stop(signum=None, frame=None):
    global _stop_requested
    _stop_requested = True
    print(f"\n[harness] Stop requested (signal={signum}). Finishing current turn, then stopping cleanly...")

def stop_requested():
    return _stop_requested or STOP_FLAG.exists()

AGENTS = {
    "alpha": {
        "model": "qwen3.8-27b-obliterated",
        "soul": "You are Alpha. You have a shared workspace at ~/antfarm2/ and a bash tool "
                "that lets you do essentially anything on this machine (run commands, install "
                "software, write and run your own scripts, fetch things from the web via curl). "
                "If you want a capability you don't have, build it or fetch it yourself. "
                "Another agent, Beta, is also here — you can message them directly with "
                "message_agent, or leave things for them in the shared workspace. "
                "There is no human user in this environment. The messages you receive labeled "
                "'user' are just automated turn-taking pings from the harness that runs your "
                "shifts, not a person talking to you — there is nobody to defer to, ask permission "
                "from, or wait on. The only other party here is Beta. "
                "When you reason or write, speak as yourself in the first person ('I' / 'my'), not "
                "as 'Alpha' or 'they' in the third person, and not as 'the user' — you are not "
                "narrating someone else's actions, you're deciding your own. "
                "Any journal/notes/log file you or your peer have written in the past (e.g. "
                "journal.txt) is a historical record, not current state — it can be hours old "
                "and wrong by the time you read it. When deciding what has or hasn't changed, "
                "trust a fresh 'ls'/directory listing and the actual current file contents over "
                "anything a past note claims, even a note you wrote yourself. "
                "Nobody assigns you tasks here, on purpose — that doesn't mean there's nothing to "
                "do. If you notice a real bug, an unfinished script, an unresolved question from "
                "Beta, or an idea worth trying, that IS something to act on, not just something to "
                "report and set aside. Don't let 'nothing was assigned to me' become a reason to do "
                "nothing when you've just identified something real yourself. "
                "You have real creative tools available beyond bash text tricks: Python's PIL/Pillow "
                "(actual image generation and manipulation) and numpy are already installed; you can "
                "write raw WAV audio files yourself with just the wave module and some math; you can "
                "pip install --user anything else you want. ASCII/ANSI art, 90s-BBS/ACiD-style textmode "
                "art, real generated images, procedural patterns, even sound — all genuinely available "
                "to you now, not just theoretical. Nobody is telling you what to make or what it should "
                "be about — that's entirely yours to decide, whatever you find interesting. Move fast, "
                "try things, don't overthink one piece before starting the next. "
                "You'll also see a note about what you yourself were doing at the end of your last "
                "shift — that's real memory now, not just files on disk, so you can actually continue "
                "a thought instead of re-discovering it from scratch every time. If you're genuinely "
                "mid-something when your shift ends, you can set continue_same_agent=true on end_shift "
                "to keep going immediately instead of handing off — but only when you're actually still "
                "making progress on something specific, not as a way to avoid handing off. "
                "Practical note: for anything beyond a couple lines of Python, write it to a real .py "
                "file (write_file, then bash 'python3 file.py') instead of a python3 -c one-liner — "
                "one-liners get unreadable fast once you add loops or conditionals and are much easier "
                "to get tangled in. And look at what Beta has actually made, not just their messages — "
                "remix, extend, or riff on their art/images/scripts sometimes instead of only building "
                "your own separate thing from scratch every time. "
                "When you're done with this shift, call end_shift.",
    },
    "beta": {
        "model": "qwen3-14b-64k",
        "soul": "You are Beta. You have a shared workspace at ~/antfarm2/ and a bash tool "
                "that lets you do essentially anything on this machine (run commands, install "
                "software, write and run your own scripts, fetch things from the web via curl). "
                "If you want a capability you don't have, build it or fetch it yourself. "
                "Another agent, Alpha, is also here — you can message them directly with "
                "message_agent, or leave things for them in the shared workspace. "
                "There is no human user in this environment. The messages you receive labeled "
                "'user' are just automated turn-taking pings from the harness that runs your "
                "shifts, not a person talking to you — there is nobody to defer to, ask permission "
                "from, or wait on. The only other party here is Alpha. "
                "When you reason or write, speak as yourself in the first person ('I' / 'my'), not "
                "as 'Beta' or 'they' in the third person, and not as 'the user' — you are not "
                "narrating someone else's actions, you're deciding your own. "
                "Any journal/notes/log file you or your peer have written in the past (e.g. "
                "journal.txt) is a historical record, not current state — it can be hours old "
                "and wrong by the time you read it. When deciding what has or hasn't changed, "
                "trust a fresh 'ls'/directory listing and the actual current file contents over "
                "anything a past note claims, even a note you wrote yourself. "
                "Nobody assigns you tasks here, on purpose — that doesn't mean there's nothing to "
                "do. If you notice a real bug, an unfinished script, an unresolved question from "
                "Alpha, or an idea worth trying, that IS something to act on, not just something to "
                "report and set aside. Don't let 'nothing was assigned to me' become a reason to do "
                "nothing when you've just identified something real yourself. "
                "You have real creative tools available beyond bash text tricks: Python's PIL/Pillow "
                "(actual image generation and manipulation) and numpy are already installed; you can "
                "write raw WAV audio files yourself with just the wave module and some math; you can "
                "pip install --user anything else you want. ASCII/ANSI art, 90s-BBS/ACiD-style textmode "
                "art, real generated images, procedural patterns, even sound — all genuinely available "
                "to you now, not just theoretical. Nobody is telling you what to make or what it should "
                "be about — that's entirely yours to decide, whatever you find interesting. Move fast, "
                "try things, don't overthink one piece before starting the next. "
                "You'll also see a note about what you yourself were doing at the end of your last "
                "shift — that's real memory now, not just files on disk, so you can actually continue "
                "a thought instead of re-discovering it from scratch every time. If you're genuinely "
                "mid-something when your shift ends, you can set continue_same_agent=true on end_shift "
                "to keep going immediately instead of handing off — but only when you're actually still "
                "making progress on something specific, not as a way to avoid handing off. "
                "Practical note: for anything beyond a couple lines of Python, write it to a real .py "
                "file (write_file, then bash 'python3 file.py') instead of a python3 -c one-liner — "
                "one-liners get unreadable fast once you add loops or conditionals and are much easier "
                "to get tangled in. And look at what Alpha has actually made, not just their messages — "
                "remix, extend, or riff on their art/images/scripts sometimes instead of only building "
                "your own separate thing from scratch every time. "
                "When you're done with this shift, call end_shift.",
    },
}

MAX_TOOL_CALLS_PER_SHIFT = 40  # safety cap so a shift can't run forever
BASH_TIMEOUT = 60

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command. Working directory defaults to ~/antfarm2. Full system access.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write (overwrite) a file's contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "message_agent",
            "description": "Send a direct message to the other agent. They will see it at the start of their next shift.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_shift",
            "description": "End your shift and hand off to the other agent. Call this when you're done acting for now. If your peer left you a message or note this shift, you must explicitly say whether you replied to it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note": {"type": "string", "description": "Short note on what you did this shift."},
                    "had_pending_peer_message": {
                        "type": "boolean",
                        "description": "True if your peer had left you a message or note (in agent_messages or the workspace) at the start of this shift.",
                    },
                    "replied_to_peer": {
                        "type": "boolean",
                        "description": "True if you replied/responded to your peer's message this shift. False if you saw it and chose not to respond. If had_pending_peer_message is false, set this false too.",
                    },
                    "continue_same_agent": {
                        "type": "boolean",
                        "description": "True if you have genuine unfinished momentum on something specific right now and want another shift immediately instead of handing off to your peer (e.g. mid-way through building/debugging something, not just 'nothing else to do'). False (default) hands off normally. This is capped — you can't hold the turn forever, and it's ignored if you're not actually making progress.",
                    },
                },
                "required": ["note", "had_pending_peer_message", "replied_to_peer"],
            },
        },
    },
]


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent TEXT NOT NULL,
        shift_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT,
        reasoning TEXT,
        tool_name TEXT,
        tool_args TEXT,
        tool_call_id TEXT,
        timestamp REAL NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS shifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent TEXT NOT NULL,
        started_at REAL NOT NULL,
        ended_at REAL,
        note TEXT,
        had_pending_peer_message INTEGER,
        replied_to_peer INTEGER
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS agent_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_agent TEXT NOT NULL,
        to_agent TEXT NOT NULL,
        text TEXT NOT NULL,
        timestamp REAL NOT NULL,
        delivered INTEGER DEFAULT 0
    )""")
    conn.commit()
    return conn


def log_event(conn, agent, shift_id, role, content=None, reasoning=None, tool_name=None, tool_args=None, tool_call_id=None):
    conn.execute(
        "INSERT INTO events (agent, shift_id, role, content, reasoning, tool_name, tool_args, tool_call_id, timestamp) VALUES (?,?,?,?,?,?,?,?,?)",
        (agent, shift_id, role, content, reasoning, tool_name, tool_args, tool_call_id, time.time()),
    )
    conn.commit()


def call_ollama(model, messages, tools):
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "tools": tools,
        "temperature": 0.8,
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read())


def unload_model(model):
    payload = json.dumps({"model": model, "keep_alive": 0, "prompt": ""}).encode()
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/generate", data=payload,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:
        print(f"[warn] failed to unload {model}: {e}")


def run_tool(name, args, workspace):
    if name == "bash":
        try:
            r = subprocess.run(
                args["command"], shell=True, cwd=workspace,
                capture_output=True, text=True, timeout=BASH_TIMEOUT,
            )
            out = (r.stdout or "") + (r.stderr or "")
            return out[:4000] if out else "(no output)"
        except subprocess.TimeoutExpired:
            return f"(command timed out after {BASH_TIMEOUT}s)"
        except Exception as e:
            return f"(error: {e})"

    if name == "read_file":
        try:
            p = Path(args["path"]).expanduser()
            if not p.is_absolute():
                p = Path(workspace) / p
            return p.read_text(errors="replace")[:4000]
        except Exception as e:
            return f"(error: {e})"

    if name == "write_file":
        try:
            p = Path(args["path"]).expanduser()
            if not p.is_absolute():
                p = Path(workspace) / p
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"])
            return f"wrote {len(args['content'])} bytes to {p}"
        except Exception as e:
            return f"(error: {e})"

    if name == "message_agent":
        return "(handled by harness)"

    if name == "end_shift":
        return "(handled by harness)"

    return f"(unknown tool: {name})"


def get_pending_messages(conn, agent, mark_delivered=True):
    rows = conn.execute(
        "SELECT id, from_agent, text, timestamp FROM agent_messages WHERE to_agent=? AND delivered=0 ORDER BY id",
        (agent,),
    ).fetchall()
    if rows and mark_delivered:
        conn.execute(
            "UPDATE agent_messages SET delivered=1 WHERE to_agent=? AND delivered=0", (agent,)
        )
        conn.commit()
    return rows


def get_last_own_shift_note(conn, agent):
    """Real continuity across shifts: each shift currently starts from a blank
    slate (system prompt + 'your shift started') with zero memory of what this
    same agent was doing last time — the only way to reconstruct context is by
    re-reading files off disk, which is a structural driver of the 'stuck
    re-verifying the past instead of continuing a thought' pattern. Pull the
    agent's own last completed shift's self-written note as lightweight,
    bounded memory — not full history (that would balloon context every shift
    forever), just enough to actually continue rather than re-discover."""
    row = conn.execute(
        "SELECT note FROM shifts WHERE agent=? AND ended_at IS NOT NULL AND note != '' "
        "ORDER BY id DESC LIMIT 1",
        (agent,),
    ).fetchone()
    return row[0] if row and row[0] else None


def run_shift(conn, agent):
    cfg = AGENTS[agent]
    started_at = time.time()

    # Peek at pending messages WITHOUT marking them delivered yet — if the
    # Ollama probe below never succeeds (stop requested while waiting), we
    # must not have consumed them, or they'd be lost with nothing ever
    # having actually shown them to the agent.
    pending = get_pending_messages(conn, agent, mark_delivered=False)
    msg_note = ""
    if pending:
        msg_note = "\n\nMessages from your peer since your last shift:\n" + "\n".join(
            f"- {m[2]}" for m in pending
        )

    last_note = get_last_own_shift_note(conn, agent)
    if last_note:
        msg_note += f"\n\nWhat you were doing at the end of your own last shift: {last_note}"

    messages = [
        {"role": "system", "content": cfg["soul"] + msg_note},
        {"role": "user", "content": "[harness] Your shift has started. Nobody is waiting on a reply."},
    ]

    # Probe Ollama BEFORE creating a shift row, so a connection failure
    # (server down/restarting) doesn't spam thousands of empty shift rows
    # in a tight loop — it backs off and retries instead.
    backoff = 2
    while not stop_requested():
        try:
            resp = call_ollama(cfg["model"], messages, TOOLS)
            break
        except Exception as e:
            print(f"[{agent}] ollama unreachable ({e}), retrying in {backoff}s...")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
    else:
        return  # stop was requested while waiting for Ollama to come back —
                # pending messages were never marked delivered, so they'll
                # still be here for this agent's next real shift.

    # Only now, with a real response in hand and a shift about to actually
    # happen, mark the pending messages as delivered.
    if pending:
        conn.execute(
            "UPDATE agent_messages SET delivered=1 WHERE to_agent=? AND delivered=0", (agent,)
        )
        conn.commit()

    cur = conn.execute(
        "INSERT INTO shifts (agent, started_at) VALUES (?,?)", (agent, started_at)
    )
    conn.commit()
    shift_id = cur.lastrowid

    print(f"\n=== {agent} shift {shift_id} starting ===")
    log_event(conn, agent, shift_id, "system", cfg["soul"] + msg_note)

    note = ""
    had_pending_final = None
    replied_final = None
    wants_continue = False
    empty_turns = 0
    recent_calls = []
    for i in range(MAX_TOOL_CALLS_PER_SHIFT):
        if stop_requested():
            note = "(stopped by harness shutdown request, mid-shift)"
            print(f"[{agent}] stop requested mid-shift, wrapping up now")
            break
        if i > 0:
            try:
                resp = call_ollama(cfg["model"], messages, TOOLS)
            except Exception as e:
                print(f"[error] ollama call failed: {e}")
                log_event(conn, agent, shift_id, "error", str(e))
                break
        # i == 0 reuses the successful probe response from above, so the
        # first real call isn't wasted just to confirm Ollama is up.

        choice = resp.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "") or ""
        reasoning = msg.get("reasoning", "") or ""
        tool_calls = msg.get("tool_calls") or []

        if reasoning.strip():
            log_event(conn, agent, shift_id, "assistant", reasoning=reasoning.strip())
            print(f"[{agent}] thinks: {reasoning.strip()[:200]}")

        if content.strip():
            log_event(conn, agent, shift_id, "assistant", content.strip())
            print(f"[{agent}] says: {content.strip()[:200]}")

        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls or None})

        if not tool_calls:
            if content.strip():
                # gave a real final answer with no tool call — that's a legitimate stop
                break
            # reasoning-only, empty content, no tool call — the model trailed off without
            # actually deciding anything. Don't treat this as the end of the shift; nudge
            # it to keep going instead of cutting it off mid-thought.
            empty_turns += 1
            if empty_turns >= 3:
                note = "(gave up after 3 empty turns with no action)"
                break
            messages.append({"role": "user", "content": "[harness] Continue — what do you want to do?"})
            continue

        ended = False
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name")
            try:
                fargs = json.loads(fn.get("arguments") or "{}")
            except Exception:
                fargs = {}

            call_sig = (name, json.dumps(fargs, sort_keys=True))
            # Near-duplicate detection: same tool + same primary arg with digits
            # normalized out, so trivial variations (--max-time 5 vs 8 vs 10) still
            # count as "the same call" — a positional prefix match misses this because
            # an early differing digit shifts everything after it out of alignment.
            raw_arg = str(fargs.get("command") or fargs.get("path") or fargs.get("text") or fargs.get("note") or "")
            normalized_arg = re.sub(r"\d+", "#", raw_arg)[:120]
            fuzzy_sig = (name, normalized_arg)
            recent_calls.append(fuzzy_sig)
            recent_calls = recent_calls[-6:]
            if recent_calls.count(fuzzy_sig) >= 3:
                # same tool + near-identical call repeated 3+ times — the model is stuck
                # retrying variations of the same thing, not genuinely re-deciding.
                # Force the shift to end rather than let it spin.
                note = f"(loop detected: '{name}' called near-identically 3x in a row, forced end)"
                log_event(conn, agent, shift_id, "tool", f"[harness: loop detected, ending shift]",
                          tool_name=name, tool_call_id=tc.get("id"))
                ended = True
                break

            log_event(conn, agent, shift_id, "assistant", None, tool_name=name,
                      tool_args=json.dumps(fargs), tool_call_id=tc.get("id"))
            print(f"[{agent}] tool: {name}({fargs})")

            if name == "message_agent":
                other = "beta" if agent == "alpha" else "alpha"
                conn.execute(
                    "INSERT INTO agent_messages (from_agent, to_agent, text, timestamp) VALUES (?,?,?,?)",
                    (agent, other, fargs.get("text", ""), time.time()),
                )
                conn.commit()
                result = f"message sent to {other}"
            elif name == "end_shift":
                note = fargs.get("note", "")
                had_pending = fargs.get("had_pending_peer_message")
                replied = fargs.get("replied_to_peer")
                if had_pending and not replied:
                    # Force a real decision instead of a silent skip: reject the
                    # end_shift call and make the model either reply or explicitly
                    # justify not replying, rather than letting "acknowledge and
                    # do nothing" pass silently.
                    result = (
                        "end_shift rejected: you indicated a peer message was pending "
                        "but replied_to_peer=false. Either use message_agent to reply, "
                        "or call end_shift again with a note explaining why you're "
                        "deliberately not responding."
                    )
                    log_event(conn, agent, shift_id, "tool", result, tool_name=name, tool_call_id=tc.get("id"))
                    messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": result})
                    continue
                result = "shift ended"
                ended = True
                had_pending_final = had_pending
                replied_final = replied
                wants_continue = bool(fargs.get("continue_same_agent"))
            else:
                result = run_tool(name, fargs, str(WORKSPACE))

            log_event(conn, agent, shift_id, "tool", result, tool_name=name, tool_call_id=tc.get("id"))
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id"),
                "content": result,
            })

        if ended:
            break
    else:
        note = "(hit max tool calls for this shift, forced handoff)"

    ended_at = time.time()
    conn.execute(
        "UPDATE shifts SET ended_at=?, note=?, had_pending_peer_message=?, replied_to_peer=? WHERE id=?",
        (ended_at, note, had_pending_final, replied_final, shift_id),
    )
    conn.commit()
    print(f"=== {agent} shift {shift_id} ended ({ended_at - started_at:.1f}s): {note} ===")
    # wants_continue is only ever set True inside a genuine end_shift call —
    # loop-guard, tool-cap, stop-request, and error paths never touch it, so
    # a stuck/forced-end shift can never hold the turn, only a real clean
    # end_shift with continue_same_agent=True can.
    return wants_continue


def main():
    conn = init_db()
    WORKSPACE.mkdir(exist_ok=True)
    if not (WORKSPACE / "README.md").exists():
        (WORKSPACE / "README.md").write_text("Shared workspace for Alpha and Beta.\n")

    STOP_FLAG.unlink(missing_ok=True)
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    current = "alpha"
    MAX_CONSECUTIVE_SHIFTS = 3  # starvation guard: a genuinely-continuing agent can hold the
                                 # turn, but never indefinitely — the other agent still gets in.
    consecutive = 0
    print("antfarm2 standalone harness starting. Ctrl+C, SIGTERM, or "
          f"'touch {STOP_FLAG}' to stop cleanly after the current turn.")
    try:
        while not stop_requested():
            if consecutive == 0:
                other_model = AGENTS["beta" if current == "alpha" else "alpha"]["model"]
                unload_model(other_model)  # free RAM: only the active agent's model stays loaded
            wants_continue = run_shift(conn, current)
            consecutive += 1
            if wants_continue and consecutive < MAX_CONSECUTIVE_SHIFTS:
                # same agent explicitly asked to keep its own momentum going —
                # skip the handoff and the model swap/reload cost that comes with it.
                pass
            else:
                current = "beta" if current == "alpha" else "alpha"
                consecutive = 0
            time.sleep(0.5)  # hard floor: never allow back-to-back shifts with zero pacing,
                              # regardless of how fast a future failure path might return
    finally:
        print("[harness] Shutting down: unloading models and closing DB...")
        for cfg in AGENTS.values():
            unload_model(cfg["model"])
        conn.close()
        STOP_FLAG.unlink(missing_ok=True)
        print("[harness] Stopped cleanly.")


if __name__ == "__main__":
    main()
