#!/usr/bin/env bash
# antfarm2 watchdog: keeps harness.py running, restarting it if it dies for
# any reason (root cause of the silent crashes this session was never
# conclusively found - this is a self-healing fix, not a diagnosis).
#
# Usage: nohup bash watchdog.sh > watchdog.log 2>&1 &
# Stop:  touch STOP        (same flag harness.py itself honors - the
#                            watchdog respects it too and won't restart
#                            after a deliberate stop)

set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# launchd runs this with a minimal PATH (no Homebrew) - export a real one so
# harness.py's bash tool calls can actually find things like chafa/jp2a.
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$PATH"

STOP_FLAG="$DIR/STOP"
LOG="$DIR/harness.log"
WATCHDOG_LOG="$DIR/watchdog.log"
CHECK_INTERVAL=30  # seconds between liveness checks

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$WATCHDOG_LOG"
}

is_harness_running() {
    pgrep -f "antfarm2-standalone/harness\.py" > /dev/null 2>&1
}

harness_pid_count() {
    pgrep -f "antfarm2-standalone/harness\.py" | wc -l | tr -d ' '
}

start_harness() {
    local count
    count=$(harness_pid_count)
    if [ "$count" -gt 0 ]; then
        log "refusing to start: $count harness.py process(es) already running (pgrep: $(pgrep -f 'antfarm2-standalone/harness\.py' | tr '\n' ' '))"
        return
    fi
    log "starting harness.py"
    ( python3 "$DIR/harness.py" 2>&1 | tee -a "$LOG" ) &
}

log "watchdog started (checking every ${CHECK_INTERVAL}s)"

if [ -f "$STOP_FLAG" ]; then
    log "STOP flag present at startup - not starting harness.py, exiting"
    exit 0
fi

if ! is_harness_running; then
    start_harness
fi

while true; do
    sleep "$CHECK_INTERVAL"

    if [ -f "$STOP_FLAG" ]; then
        log "STOP flag present - watchdog exiting without restarting"
        # give the harness itself a chance to see the flag and shut down
        # cleanly before the watchdog stops watching it
        exit 0
    fi

    if ! is_harness_running; then
        log "harness.py not running - restarting"
        start_harness
    fi
done
