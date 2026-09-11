# launchd setup

Both the dashboard and the watchdog (which supervises harness.py) now run as
real macOS launchd agents, not as ad-hoc background shell processes. This is
what actually keeps them running across terminal sessions, tool restarts,
crashes, and reboots.

## Why this exists
Processes started as plain background shell jobs (even nohup/disown'd ones)
were dying silently with no OS-level signal logged anywhere - no SIGTERM, no
SIGKILL, no OOM/jetsam. The likely cause: their lifetime was tied to
whatever spawned them, not to a real daemon supervisor. launchd (PID 1) is
immune to that.

## Install
    cp launchd/com.antfarm2.dashboard.plist ~/Library/LaunchAgents/
    cp launchd/com.antfarm2.watchdog.plist ~/Library/LaunchAgents/
    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.antfarm2.dashboard.plist
    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.antfarm2.watchdog.plist

## Check status
    launchctl list | grep antfarm2

## Stop supervision entirely (e.g. before manual debugging)
    launchctl bootout gui/$(id -u)/com.antfarm2.dashboard
    launchctl bootout gui/$(id -u)/com.antfarm2.watchdog

Normal stop/start/restart should go through the dashboard control panel
(/api/control/*) or `touch STOP` - launchd will notice the clean exit and,
for the watchdog, respect the STOP flag exactly like before. KeepAlive is
configured to only restart on non-clean exit, not after every stop.
