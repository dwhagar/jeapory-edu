#!/bin/bash
# Click target for the Chromebook (Crostini/Linux) desktop launcher --
# see jeopardy.desktop.template and install.sh.
#
# Idempotent by design: starts the server only if one isn't already running
# on the configured port, then opens/focuses a browser window. It never
# tries to stop the server on exit -- Chrome/Chromium share one process per
# profile, so a second "open browser" invocation just hands the URL to the
# already-running Chrome and returns immediately; there is no reliable way
# to detect "the user closed that window" from here. Shutting the server
# down remains the job of the existing in-app Exit button (POST /api/exit).

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8000}"
URL="http://127.0.0.1:${PORT}/"
LIVENESS_URL="http://127.0.0.1:${PORT}/api/rounds"
LOG_FILE="/tmp/jeopardy_launch.log"

is_server_up() {
    curl -s -o /dev/null -w "%{http_code}" "$LIVENESS_URL" 2>/dev/null | grep -q "^200$"
}

start_server() {
    echo "Starting Classroom Jeopardy server..." >>"$LOG_FILE"
    (cd "$SCRIPT_DIR" && nohup python3 server.py >>"$LOG_FILE" 2>&1 &)
}

open_browser() {
    if command -v xdg-open >/dev/null 2>&1 && xdg-open "$URL" 2>>"$LOG_FILE"; then
        return 0
    fi
    # Fallback: only reached if xdg-open is missing/fails. On a stock
    # Crostini container this normally shouldn't happen -- xdg-open is how
    # the Linux VM hands a URL off to the host Chrome OS browser.
    for browser in google-chrome chromium chromium-browser; do
        if command -v "$browser" >/dev/null 2>&1; then
            "$browser" --app="$URL" >>"$LOG_FILE" 2>&1 &
            return 0
        fi
    done
    return 1
}

if is_server_up; then
    echo "Server already running on port $PORT." >>"$LOG_FILE"
else
    start_server
    ready=0
    for _ in $(seq 1 10); do
        sleep 1
        if is_server_up; then
            ready=1
            break
        fi
    done
    if [ "$ready" -ne 1 ]; then
        echo "Server did not come up within 10s; see $LOG_FILE" >>"$LOG_FILE"
        if command -v notify-send >/dev/null 2>&1; then
            notify-send "Classroom Jeopardy" "Server failed to start -- see $LOG_FILE"
        fi
        exit 1
    fi
fi

if ! open_browser; then
    echo "Could not find a way to open a browser (no xdg-open, no Chrome/Chromium)." >>"$LOG_FILE"
    if command -v notify-send >/dev/null 2>&1; then
        notify-send "Classroom Jeopardy" "Server is running at $URL but no browser could be opened automatically."
    fi
    exit 1
fi

exit 0
