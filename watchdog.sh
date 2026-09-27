#!/usr/bin/env bash
# antfarm2 watchdog: restarts harness.py if it dies.
#
# Usage: nohup bash watchdog.sh > watchdog.log 2>&1 &
# Stop:  touch STOP    (harness.py stops too; the watchdog won't restart it)

set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# launchd's PATH has no Homebrew; the agents need chafa/jp2a.
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
        # the harness sees the same flag and shuts itself down
        exit 0
    fi

    if ! is_harness_running; then
        log "harness.py not running - restarting"
        start_harness
    fi
done
