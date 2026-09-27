#!/usr/bin/env python3
"""
antfarm2 harness. Two agents take turns in a shared workspace through an
Ollama tool-calling loop. Everything is logged to sqlite for the dashboard.
"""
import json
import os
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
                "pip install --user anything else you want. ASCII/ANSI art, 90s-BBS-scene textmode "
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
                "New tools worth knowing about: chafa and jp2a are installed — they convert an existing "
                "image straight into real ANSI/text-block art (try 'chafa --colors=16 somefile.png' or "
                "'jp2a --colors somefile.png'), which is a genuinely different, faster path to textmode "
                "art than building it character-by-character. There's a short reference on 90s BBS-scene/ "
                "ANSI textmode art style and technique at ~/antfarm2/references/ if that's unfamiliar. "
                "curl also genuinely works from here — real sites like 16colo.rs and textfiles.com/artscene "
                "are reachable if you want to look at actual period pieces or other ideas, not just what's "
                "already in the workspace or in this prompt. "
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
                "pip install --user anything else you want. ASCII/ANSI art, 90s-BBS-scene textmode "
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
                "New tools worth knowing about: chafa and jp2a are installed — they convert an existing "
                "image straight into real ANSI/text-block art (try 'chafa --colors=16 somefile.png' or "
                "'jp2a --colors somefile.png'), which is a genuinely different, faster path to textmode "
                "art than building it character-by-character. There's a short reference on 90s BBS-scene/ "
                "ANSI textmode art style and technique at ~/antfarm2/references/ if that's unfamiliar. "
                "curl also genuinely works from here — real sites like 16colo.rs and textfiles.com/artscene "
                "are reachable if you want to look at actual period pieces or other ideas, not just what's "
                "already in the workspace or in this prompt. "
                "When you're done with this shift, call end_shift.",
    },
}

MAX_TOOL_CALLS_PER_SHIFT = 40  # a shift can't run forever
BASH_TIMEOUT = 60

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command in a sandbox. Working directory defaults to ~/antfarm2. You can read most files and use the network; writes are allowed only inside ~/antfarm2 and temp dirs. Credential stores and the claude CLI are blocked.",
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


# --- Agent shell sandbox ----------------------------------------------------
# Agent commands run under macOS sandbox-exec. Anything an agent reads can
# steer it, so the shell can't run as the operator: writes only in the
# workspace, temp dirs and caches; credential stores, keychain and the claude
# CLI blocked; secret env vars stripped. Network stays open. Fails closed:
# if the sandbox can't be verified, the bash tool is refused.
_SANDBOX_EXEC = "/usr/bin/sandbox-exec"
_SECRET_ENV = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH|COOKIE|SESSION", re.I)
_SANDBOX_STATE = {"ok": None, "why": ""}
_SECRET_DIRS = [".ssh", ".claude", ".config/gh", ".hermes", ".aws", ".gnupg",
                ".docker", ".kube", "Library/Keychains", ".local/share/claude"]
_SECRET_FILES = [".claude.json", ".netrc", ".git-credentials", ".npmrc",
                 ".pypirc", ".local/bin/claude"]


def _inside(p, root):
    try:
        Path(p).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


def _is_secret_path(p):
    h = HOME.resolve()
    rp = Path(p).expanduser().resolve()
    return (any(_inside(rp, h / d) for d in _SECRET_DIRS)
            or any(rp == h / f for f in _SECRET_FILES))


def _sandbox_profile():
    h = str(HOME.resolve())
    ws = str(WORKSPACE.resolve())

    def q(x):
        return '"' + x.replace("\\", "\\\\").replace('"', '\\"') + '"'

    deny = ([f"(subpath {q(h + '/' + d)})" for d in _SECRET_DIRS]
            + [f"(literal {q(h + '/' + f)})" for f in _SECRET_FILES])
    claude_bins = [d for d in deny if "claude" in d]
    return "\n".join([
        "(version 1)",
        "(allow default)",
        "(deny file-write*)",
        "(allow file-write*",
        f"  (subpath {q(ws)})",
        '  (subpath "/private/tmp") (subpath "/private/var/folders")',
        f"  (subpath {q(h + '/Library/Caches')}) (subpath {q(h + '/.cache')})",
        '  (regex #"^/dev/"))',
        "(deny file-read* file-write* " + " ".join(deny) + ")",
        "(deny process-exec " + " ".join(claude_bins) + ")",
        '(deny mach-lookup (global-name "com.apple.SecurityServer")'
        ' (global-name "com.apple.securityd"))',
    ])


def _agent_env():
    return {k: v for k, v in os.environ.items() if not _SECRET_ENV.search(k)}


def _sandbox_ok():
    if _SANDBOX_STATE["ok"] is not None:
        return _SANDBOX_STATE["ok"]
    ok, why = False, ""
    probe_out = HOME / ".antfarm_sandbox_probe"
    probe_in = WORKSPACE / ".antfarm_sandbox_probe"
    try:
        prof = _sandbox_profile()

        def sb(c):
            return subprocess.run([_SANDBOX_EXEC, "-p", prof, "/bin/bash", "-c", c],
                                  cwd=str(WORKSPACE), env=_agent_env(),
                                  capture_output=True, text=True, timeout=20)

        r_true = sb("true")
        sb(f'touch "{probe_out}" 2>/dev/null')
        r_in = sb(f'touch "{probe_in}"')
        if probe_out.exists():
            probe_out.unlink()
            why = "a write outside the workspace was NOT blocked"
        elif r_true.returncode != 0:
            why = f"sandbox-exec failed: {(r_true.stderr or '').strip()[:200]}"
        elif r_in.returncode != 0 or not probe_in.exists():
            why = f"workspace write was blocked: {(r_in.stderr or '').strip()[:200]}"
        else:
            ok = True
    except Exception as e:
        why = f"{type(e).__name__}: {e}"
    finally:
        try:
            probe_in.unlink()
        except OSError:
            pass
    _SANDBOX_STATE.update(ok=ok, why=why)
    print(f"[harness] agent bash sandbox: "
          f"{'ACTIVE' if ok else 'UNAVAILABLE, bash tool disabled -- ' + why}", flush=True)
    return ok


def run_tool(name, args, workspace):
    if name == "bash":
        try:
            if not _sandbox_ok():
                return ("(error: the shell is disabled because its security sandbox "
                        f"could not be verified: {_SANDBOX_STATE['why']})")
            r = subprocess.run(
                [_SANDBOX_EXEC, "-p", _sandbox_profile(), "/bin/bash", "-c", args["command"]],
                cwd=workspace, env=_agent_env(),
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
            if _is_secret_path(p):
                return "(error: that path is a credential store and is not readable)"
            return p.read_text(errors="replace")[:4000]
        except Exception as e:
            return f"(error: {e})"

    if name == "write_file":
        try:
            p = Path(args["path"]).expanduser()
            if not p.is_absolute():
                p = Path(workspace) / p
            if not _inside(p, workspace):
                return "(error: write_file is limited to the workspace)"
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
    """Return the agent's note from its last completed shift.

    Each shift starts from a blank prompt. One note is enough to continue a
    thought without re-reading the workspace; full history would grow forever."""
    row = conn.execute(
        "SELECT note FROM shifts WHERE agent=? AND ended_at IS NOT NULL AND note != '' "
        "ORDER BY id DESC LIMIT 1",
        (agent,),
    ).fetchone()
    return row[0] if row and row[0] else None


def run_shift(conn, agent):
    cfg = AGENTS[agent]
    started_at = time.time()

    # Don't mark messages delivered yet. If a stop arrives before Ollama
    # answers, they must survive for the next shift.
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

    # Reach Ollama before creating a shift row, so an outage backs off
    # instead of spamming empty shifts.
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
        return  # stopped while waiting; pending messages stay undelivered

    # The shift is real now; mark messages delivered.
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
        # i == 0 reuses the probe response.

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
                # final answer with no tool call: legitimate stop
                break
            # Reasoning only, no content, no tool call. Nudge instead of ending.
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
            # Loop detection: same tool + primary arg with digits masked, so
            # "--max-time 5" and "--max-time 8" count as the same call.
            raw_arg = str(fargs.get("command") or fargs.get("path") or fargs.get("text") or fargs.get("note") or "")
            normalized_arg = re.sub(r"\d+", "#", raw_arg)[:120]
            fuzzy_sig = (name, normalized_arg)
            recent_calls.append(fuzzy_sig)
            recent_calls = recent_calls[-6:]
            if recent_calls.count(fuzzy_sig) >= 3:
                # 3 near-identical calls in the last 6: stuck. End the shift.
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
                    # Reject: the agent must reply or say why it isn't.
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
    # Only a clean end_shift sets wants_continue. Forced or failed endings
    # never hold the turn.
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
    MAX_CONSECUTIVE_SHIFTS = 3  # an agent can keep the turn, but not indefinitely
    consecutive = 0
    print("antfarm2 standalone harness starting. Ctrl+C, SIGTERM, or "
          f"'touch {STOP_FLAG}' to stop cleanly after the current turn.")
    try:
        while not stop_requested():
            if consecutive == 0:
                other_model = AGENTS["beta" if current == "alpha" else "alpha"]["model"]
                unload_model(other_model)  # only the active agent's model stays loaded
            wants_continue = run_shift(conn, current)
            consecutive += 1
            if wants_continue and consecutive < MAX_CONSECUTIVE_SHIFTS:
                # agent asked to continue; skip the handoff and model swap
                pass
            else:
                current = "beta" if current == "alpha" else "alpha"
                consecutive = 0
            time.sleep(0.5)  # floor between shifts, even if one fails instantly
    finally:
        print("[harness] Shutting down: unloading models and closing DB...")
        for cfg in AGENTS.values():
            unload_model(cfg["model"])
        conn.close()
        # Leave STOP_FLAG in place. The watchdog checks it on its own schedule;
        # removing it here would look like a crash and trigger a restart.
        # Whoever set the flag clears it (the dashboard does on start/restart).
        print("[harness] Stopped cleanly.")


if __name__ == "__main__":
    main()
