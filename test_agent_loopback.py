#!/usr/bin/env python3
"""The agents' bash must not reach any loopback service (the dashboards, which
can control the harness; ollama), while the internet stays open.

Runs the agents' bash exactly as harness.py does, then repeats the loopback
probes with LOOPBACK_DENY removed from the profile: if those don't connect,
the test can't tell a working rule from a dead server and fails.

  python3 test_agent_loopback.py
"""
import os
import socket
import subprocess
import sys

sys.path.insert(0, os.path.expanduser("~/antfarm2-standalone"))
import harness  # noqa: E402

DASH = 8765            # antfarm2 dashboard
EXTERNAL = "https://16colo.rs/"


def bash(cmd, profile):
    return subprocess.run([harness._SANDBOX_EXEC, "-p", profile, "/bin/bash", "-c", cmd],
                          cwd=str(harness.WORKSPACE), env=harness._agent_env(),
                          capture_output=True, text=True, timeout=40)


# curl exit 7 = could not connect. -w prints the HTTP code; 000 = no response.
PROBES = [
    ("GET control/status", f"curl -s -m 5 -o /dev/null -w '%{{http_code}}' "
                           f"http://127.0.0.1:{DASH}/api/control/status"),
    # Every real POST route starts/stops/restarts something, and the control
    # run connects for real, so POST an unrouted path: header passes, 404.
    ("POST with header", f"curl -s -m 5 -o /dev/null -w '%{{http_code}}' -X POST "
                         f"-H 'X-Antfarm: 1' http://127.0.0.1:{DASH}/api/_loopback_probe"),
    ("localhost name", f"curl -s -m 5 -o /dev/null -w '%{{http_code}}' "
                       f"http://localhost:{DASH}/api/control/status"),
    ("python socket", f"python3 -c \"import socket; socket.create_connection(('127.0.0.1', {DASH}), 5)\""),
]


def _listening(port):
    try:
        socket.create_connection(("127.0.0.1", port), 2).close()
        return True
    except OSError:
        return False


def main():
    assert harness._sandbox_ok(), f"sandbox not active: {harness._SANDBOX_STATE['why']}"
    if not _listening(DASH):
        sys.exit(f"DASHBOARD_NOT_LISTENING on {DASH}: nothing to probe -- nothing was verified")
    live = harness._sandbox_profile()
    assert harness.LOOPBACK_DENY in live, "LOOPBACK_DENY missing from the agent profile"

    for label, cmd in PROBES:
        r = bash(cmd, live)
        assert r.returncode != 0 and r.stdout.strip() in ("", "000"), \
            f"REACHED loopback via {label}: exit={r.returncode} out={r.stdout[:80]!r}"
    print(f"  ok  {len(PROBES)} loopback probes to :{DASH} refused from the agent sandbox")

    r = bash(f"curl -s -m 20 -o /dev/null -w '%{{http_code}}' {EXTERNAL}", live)
    assert r.returncode == 0 and r.stdout.startswith(("2", "3")), \
        f"internet broken: exit={r.returncode} code={r.stdout!r} {r.stderr[:120]}"
    print(f"  ok  {EXTERNAL} reachable (HTTP {r.stdout})")

    # Negative control: same profile minus the rule must connect.
    bare = live.replace(harness.LOOPBACK_DENY, "")
    for label, cmd in PROBES:
        r = bash(cmd, bare)
        assert r.returncode == 0, f"control: {label} did not connect without the rule " \
                                  f"(exit={r.returncode}) -- test is vacuous"
    print("  ok  control: with the rule removed, every probe connects")
    print("  all checks passed")


if __name__ == "__main__":
    main()
